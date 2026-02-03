"""Embedding Generation for RAG Pipeline"""

import os
import warnings
from typing import Optional

import numpy as np

from src.config import get_settings


class EmbeddingService:
    """
    Local embedding generation using sentence-transformers.

    Uses all-MiniLM-L6-v2 (384 dimensions) for:
    - Zero cost (no API calls)
    - Privacy (data never leaves local machine)
    - Good quality for medical/scientific text
    """

    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize embedding service.

        Args:
            model_name: Model to use (default: all-MiniLM-L6-v2)
        """
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model
        self.dimension = settings.embedding_dimension
        self._model = None

    def _load_model(self):
        """Lazy load the model to avoid startup overhead."""
        if self._model is None:
            # Suppress tokenizer warnings
            os.environ["TOKENIZERS_PARALLELISM"] = "false"

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*position_ids.*")
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)

    def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        self._load_model()
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        self._load_model()
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 10,
        )
        return [emb.tolist() for emb in embeddings]

    def similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0-1)
        """
        a = np.array(embedding1)
        b = np.array(embedding2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def get_dimension(self) -> int:
        """Return the embedding dimension."""
        return self.dimension


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create singleton embedding service."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
