"""
Embedding service — turns text into 1024-dim vectors via BGE-M3.

BGE-M3 (BAAI/bge-m3) is a multilingual dense retriever: it places text
from ~100 languages, including Sinhala, into one shared vector space.
That means an English query can retrieve chunks written in Sinhala.

Design:
- Model loads lazily on first use, so importing this module is free.
- Model is a process-wide singleton, thread-safe on load.
- First call downloads ~2 GB from HuggingFace. Subsequent calls use cache.
"""
import logging
from threading import Lock

log = logging.getLogger(__name__)


MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DIM = 1024

_model = None
_model_lock = Lock()


def _get_model():
    """Load BGE-M3 once per process. Thread-safe."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        log.info(
            f"Loading embedding model {MODEL_NAME} "
            f"(first call, may download ~2 GB)"
        )
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME, device="cpu")
        log.info(
            f"Embedding model loaded; dim = "
            f"{_model.get_sentence_embedding_dimension()}"
        )
        return _model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of document chunks."""
    if not texts:
        return []
    model = _get_model()
    # normalize_embeddings=True produces unit vectors, which is what
    # cosine distance expects (pgvector's vector_cosine_ops).
    vecs = model.encode(
        texts,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 32,
    )
    return [v.tolist() for v in vecs]


def embed_query(text: str) -> list[float]:
    """Embed a single search query."""
    model = _get_model()
    vec = model.encode([text], normalize_embeddings=True)[0]
    return vec.tolist()