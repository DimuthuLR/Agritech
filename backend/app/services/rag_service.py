"""
RAG service — retrieves relevant chunks from knowledge_documents.

Used by the diagnosis pipeline to fetch reference material before the
vision model answers. The chunks are Sri Lankan agricultural guides
(DoA publications, IPM manuals, Registrar of Pesticides lists).

Design:
- Cosine similarity via pgvector's HNSW index (fast, approximate).
- Cross-lingual: BGE-M3 maps Sinhala and English to the same vector
  space, so an English query retrieves Sinhala chunks about the same topic.
- Fail-soft: any retrieval error returns an empty list; the diagnosis
  pipeline proceeds without reference material rather than failing.
"""
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.knowledge_document import KnowledgeDocument
from app.services.embedding_service import embed_query


log = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    content: str
    source: str
    similarity: float  # 0..1, higher = more similar
    language: str
    crop: str | None
    topic: str | None


def build_query(
    plot_crop: str | None,
    notes: str | None,
) -> str:
    """
    Compose a retrieval query from the signals we have at diagnosis time.

    The query deliberately includes differentiating vocabulary (blight,
    spots, lesions, bacterial vs fungal, wilting) because the corpus
    is dominated by crop-by-crop guides with disease sections, and
    we want chunks that describe visual symptom patterns.
    """
    parts: list[str] = []
    if plot_crop:
        parts.append(plot_crop)
    parts.extend([
        "leaf disease",
        "blight",
        "brown spots",
        "lesions",
        "concentric rings",
        "yellow halo",
        "bacterial",
        "fungal",
        "symptoms",
        "identification",
        "treatment",
    ])
    if notes:
        parts.append(notes)
    return " ".join(parts)


def search(
    db: Session,
    query: str,
    *,
    crop: str | None = None,
    topic: str | None = None,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """
    Return the top-k most similar chunks for the query.

    `crop` and `topic` are optional hard filters. When None, the search
    is over the entire corpus. Hard filters are useful when the crop is
    known and you want to bias strongly; the current diagnosis pipeline
    does not use them (crop is already in the query text).
    """
    if not query or not query.strip():
        return []

    try:
        qvec = embed_query(query)
    except Exception as e:
        log.warning(f"Query embedding failed: {e}")
        return []

    stmt = select(
        KnowledgeDocument,
        KnowledgeDocument.embedding.cosine_distance(qvec).label("distance"),
    )

    if crop is not None:
        stmt = stmt.where(
            (KnowledgeDocument.crop == crop) | (KnowledgeDocument.crop.is_(None))
        )
    if topic is not None:
        stmt = stmt.where(
            (KnowledgeDocument.topic == topic) | (KnowledgeDocument.topic.is_(None))
        )

    stmt = stmt.order_by("distance").limit(top_k)

    try:
        rows = db.execute(stmt).all()
    except Exception as e:
        log.warning(f"RAG search failed: {e}")
        return []

    results: list[RetrievedChunk] = []
    for doc, distance in rows:
        # cosine_distance returns 1 - cosine_similarity, so invert it back
        similarity = 1.0 - float(distance)
        results.append(
            RetrievedChunk(
                content=doc.content,
                source=doc.source,
                similarity=similarity,
                language=doc.language,
                crop=doc.crop,
                topic=doc.topic,
            )
        )
    return results


def format_for_prompt(
    chunks: list[RetrievedChunk],
    max_chars: int = 4000,
) -> str:
    """
    Format retrieved chunks as a text block to inject into the model prompt.

    Truncates at max_chars so we don't blow the context window. Reference
    blocks are cheap relative to the value they add — 6 KB is roughly
    1500-2000 tokens.
    """
    if not chunks:
        return ""

    parts: list[str] = []
    total = 0

    for i, c in enumerate(chunks, 1):
        # Keep headers short; the model doesn't need the full source path.
        header = f"[Reference {i}] (source: {c.source}, match: {c.similarity:.0%})"
        body = c.content.strip()

        # If a single chunk is enormous, truncate it individually first.
        if len(body) > 2500:
            body = body[:2500].rstrip() + "…"

        block = f"{header}\n{body}"

        if total + len(block) > max_chars:
            break

        parts.append(block)
        total += len(block)

    return "\n\n---\n\n".join(parts)