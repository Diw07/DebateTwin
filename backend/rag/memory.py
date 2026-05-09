"""
rag/memory.py
-------------
RAG (Retrieval-Augmented Generation) layer for the User Twin.

Design decisions
~~~~~~~~~~~~~~~~
* **Abstraction boundary**: The public interface is ``PersonaMemory``, a class
  with two methods: ``ingest`` and ``retrieve``.  Swapping ChromaDB for a
  Pinecone, Weaviate, or a C++ HNSW engine only requires a new implementation
  of the same interface — the agent layer never touches ChromaDB directly.

* **Embedding model**: sentence-transformers running locally.  No external API
  call for embeddings, no cost, no rate-limiting.  Model is configurable via
  ``EMBEDDING_MODEL`` env var.

* **Chunking strategy**: Overlapping sliding window (512 tokens / 64 overlap)
  balances retrieval precision with context richness.

* **Metadata filtering**: Every chunk is tagged with ``persona_id`` so a
  single ChromaDB collection can host multiple user personas without bleed.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Protocol

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

from schemas import DocumentChunk, RAGResult
from utils import get_logger, get_settings

logger = get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Abstract retrieval interface — swap implementation without touching agents
# ---------------------------------------------------------------------------

class RetrievalBackend(Protocol):
    """
    Structural protocol for vector-store backends.
    Any class implementing ``ingest`` and ``retrieve`` satisfies this.
    """

    def ingest(self, text: str, source_file: str, persona_id: str) -> int:
        """Ingest raw text; returns number of chunks stored."""
        ...

    def retrieve(self, query: str, persona_id: str, top_k: int = 4) -> RAGResult:
        """Return the top-k most relevant chunks for a query."""
        ...


# ---------------------------------------------------------------------------
# Text chunking helpers
# ---------------------------------------------------------------------------

def _chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[str]:
    """
    Split text into overlapping token-approximate chunks.

    We approximate token count via word count (1 word ≈ 1.3 tokens).
    For production, replace with ``tiktoken`` for exact tokenisation.
    """
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start += chunk_size - overlap

    return chunks


def _clean_text(text: str) -> str:
    """Normalise whitespace and strip control characters."""
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# PDF extraction (optional dependency)
# ---------------------------------------------------------------------------

def _extract_pdf_text(file_path: Path) -> str:
    """Extract raw text from a PDF using pypdf."""
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required for PDF ingestion: pip install pypdf"
        ) from exc


# ---------------------------------------------------------------------------
# ChromaDB-backed implementation
# ---------------------------------------------------------------------------

class ChromaPersonaMemory:
    """
    Concrete ``RetrievalBackend`` using ChromaDB + sentence-transformers.

    Lifecycle
    ~~~~~~~~~
    1. ``__init__``: connect to (or create) the persistent ChromaDB collection.
    2. ``ingest``: chunk → embed → upsert with persona metadata.
    3. ``retrieve``: embed query → cosine search → return ``RAGResult``.

    Future extension point
    ~~~~~~~~~~~~~~~~~~~~~~
    Replace this class with ``CppHNSWMemory`` or ``MultimodalPineconeMemory``
    without changing ``agents/user_twin.py`` — the caller only sees
    ``RetrievalBackend``.
    """

    def __init__(self) -> None:
        self._embedder = SentenceTransformer(settings.embedding_model)
        logger.info("Loaded embedding model", model=settings.embedding_model)

        chroma_client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = chroma_client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB ready",
            collection=settings.chroma_collection_name,
            documents=self._collection.count(),
        )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest(self, text: str, source_file: str, persona_id: str) -> int:
        """
        Chunk, embed, and upsert text into ChromaDB.

        Returns the number of new chunks stored.
        Idempotent: re-ingesting the same file replaces existing chunks
        (identified by deterministic chunk_id).
        """
        text = _clean_text(text)
        if not text:
            logger.warning("Empty text after cleaning — skipping", source=source_file)
            return 0

        chunks = _chunk_text(text)
        logger.info("Chunked document", source=source_file, chunks=len(chunks))

        ids, embeddings, documents, metadatas = [], [], [], []

        for idx, chunk in enumerate(chunks):
            # Deterministic ID: hash of (persona + source + index)
            raw_id = f"{persona_id}::{source_file}::{idx}"
            chunk_id = hashlib.sha256(raw_id.encode()).hexdigest()[:32]

            embedding = self._embedder.encode(chunk).tolist()

            ids.append(chunk_id)
            embeddings.append(embedding)
            documents.append(chunk)
            metadatas.append(
                {
                    "persona_id": persona_id,
                    "source_file": source_file,
                    "chunk_index": idx,
                    "embedding_model": settings.embedding_model,
                }
            )

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info("Upserted chunks", count=len(ids), persona=persona_id)
        return len(ids)

    def ingest_file(self, file_path: str | Path, persona_id: str) -> int:
        """
        High-level helper: read a .txt or .pdf file and ingest it.
        Extend here to support .docx, .md, .html, etc.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = _extract_pdf_text(path)
        elif suffix in {".txt", ".md", ".rst"}:
            text = path.read_text(encoding="utf-8", errors="replace")
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        return self.ingest(text, source_file=path.name, persona_id=persona_id)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query: str, persona_id: str, top_k: int = 4) -> RAGResult:
        """
        Retrieve the most semantically relevant chunks for a query.

        Filters strictly by ``persona_id`` to prevent cross-user bleed.
        Falls back gracefully if the collection is empty.
        """
        count = self._collection.count()
        if count == 0:
            logger.warning("ChromaDB collection is empty — RAG disabled")
            return RAGResult(chunks=[], query=query, persona_id=persona_id)

        query_embedding = self._embedder.encode(query).tolist()

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, count),
            where={"persona_id": {"$eq": persona_id}},
            include=["documents", "metadatas", "distances"],
        )

        chunks: list[DocumentChunk] = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            chunk_id = results["ids"][0][i]
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    persona_id=meta["persona_id"],
                    text=doc,
                    source_file=meta["source_file"],
                    chunk_index=meta["chunk_index"],
                    embedding_model=meta["embedding_model"],
                )
            )

        logger.debug("RAG retrieved", query=query[:80], chunks=len(chunks))
        return RAGResult(chunks=chunks, query=query, persona_id=persona_id)

    def collection_count(self) -> int:
        return self._collection.count()


# ---------------------------------------------------------------------------
# Module-level singleton (lazy, thread-safe via Python's GIL for imports)
# ---------------------------------------------------------------------------

_memory_instance: ChromaPersonaMemory | None = None


def get_memory() -> ChromaPersonaMemory:
    """Return the module-level singleton PersonaMemory."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ChromaPersonaMemory()
    return _memory_instance
