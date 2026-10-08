"""
KnowledgeDocument — RAG corpus chunks with vector embeddings.

Each row is one chunk of a source document (a PDF, a manual, a web page).
Chunks are retrieved by cosine similarity against a query embedding, then
injected into the LLM prompt as reference material.

Phase 9.85b.
"""
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, Integer, DateTime, Index, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


# BGE-M3 produces 1024-dimensional dense vectors.
EMBEDDING_DIM = 1024


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # --- Source identity ---
    source: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    # Free-form string identifying where this came from:
    # e.g. "doa_chili_guide_2023.pdf" or "https://doa.gov.lk/..."
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # "pdf" | "txt" | "html" | "manual"
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # sha256 of the source file — lets us detect already-ingested docs

    # --- Human-readable metadata ---
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    language: Mapped[str] = mapped_column(
        String(8), nullable=False, default="en"
    )
    # "en" | "si" | "ta"

    # --- Domain filters (used to narrow the search before vector scoring) ---
    crop: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    # "chili" | "tomato" | "brinjal" | "cabbage" | "carrot" | None (general)
    topic: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    # "disease" | "pest" | "nutrition" | "agronomy" | None (general)

    # --- Chunk position within the source ---
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Content ---
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Embedding (1024 floats, cosine distance) ---
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=False
    )

    # --- Free-form extra metadata ---
    # "metadata_"/"metadata" pattern matches the Device model.
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    # e.g. {"page": 47, "section": "4.2 Early Blight"}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Per-source ordered lookup (re-ingesting a document, listing chunks)
        Index("ix_knowledge_documents_source_chunk", "source", "chunk_index"),
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeDocument {self.source!r} chunk {self.chunk_index} "
            f"({self.language}, topic={self.topic or 'general'})>"
        )