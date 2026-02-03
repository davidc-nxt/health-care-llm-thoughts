"""Vector Store using PostgreSQL with pgvector"""

import json
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from src.config import get_settings
from src.rag.chunking import PaperChunk
from src.rag.embeddings import EmbeddingService, get_embedding_service


class VectorStore:
    """
    PostgreSQL vector store using pgvector extension.

    Features:
    - Cosine similarity search
    - Specialty filtering
    - Metadata storage for citations
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        """
        Initialize vector store.

        Args:
            database_url: PostgreSQL connection string
            embedding_service: Service for generating embeddings
        """
        settings = get_settings()
        self._db_url = database_url or settings.database_url_sync
        self._engine = create_engine(self._db_url)
        self._embedding_service = embedding_service or get_embedding_service()

    def _format_vector_for_pg(self, vector: list[float]) -> str:
        """Format vector as PostgreSQL vector literal."""
        return "[" + ",".join(str(v) for v in vector) + "]"

    def store_paper(
        self, paper_id: str, title: str, abstract: str, **metadata
    ) -> int:
        """
        Store a research paper record.

        Args:
            paper_id: Unique paper identifier
            title: Paper title
            abstract: Paper abstract
            **metadata: Additional metadata fields

        Returns:
            Database ID of stored paper
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    text("""
                        INSERT INTO research_papers (
                            paper_id, title, abstract, authors, source,
                            specialty, publication_date, source_url, full_text
                        ) VALUES (
                            :paper_id, :title, :abstract, :authors, :source,
                            :specialty, :publication_date, :source_url, :full_text
                        )
                        ON CONFLICT (paper_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            abstract = EXCLUDED.abstract,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id
                    """),
                    {
                        "paper_id": paper_id,
                        "title": title,
                        "abstract": abstract,
                        "authors": metadata.get("authors", []),
                        "source": metadata.get("source", "unknown"),
                        "specialty": metadata.get("specialty"),
                        "publication_date": metadata.get("publication_date"),
                        "source_url": metadata.get("source_url"),
                        "full_text": metadata.get("full_text"),
                    },
                )
                conn.commit()
                return result.fetchone()[0]
        except SQLAlchemyError as e:
            print(f"Error storing paper: {e}")
            raise

    def store_chunk(self, chunk: PaperChunk, paper_db_id: int) -> int:
        """
        Store a paper chunk with its embedding.

        Args:
            chunk: PaperChunk to store
            paper_db_id: Database ID of parent paper

        Returns:
            Database ID of stored chunk
        """
        # Generate embedding
        embedding = self._embedding_service.embed_text(chunk.content)
        vector_literal = self._format_vector_for_pg(embedding)

        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    text(f"""
                        INSERT INTO paper_chunks (
                            paper_id, chunk_index, content, embedding, chunk_metadata
                        ) VALUES (
                            :paper_id, :chunk_index, :content,
                            '{vector_literal}'::vector, :metadata
                        )
                        RETURNING id
                    """),
                    {
                        "paper_id": paper_db_id,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "metadata": json.dumps(chunk.metadata),
                    },
                )
                conn.commit()
                return result.fetchone()[0]
        except SQLAlchemyError as e:
            print(f"Error storing chunk: {e}")
            raise

    def store_chunks(self, chunks: list[PaperChunk], paper_db_id: int) -> list[int]:
        """
        Store multiple chunks.

        Args:
            chunks: List of PaperChunk objects
            paper_db_id: Database ID of parent paper

        Returns:
            List of database IDs
        """
        return [self.store_chunk(chunk, paper_db_id) for chunk in chunks]

    def search(
        self,
        query: str,
        specialty: Optional[str] = None,
        top_k: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict]:
        """
        Semantic search across paper chunks.

        Args:
            query: Search query text
            specialty: Filter by medical specialty
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of search results with content, metadata, and similarity
        """
        # Generate query embedding
        query_embedding = self._embedding_service.embed_text(query)
        vector_literal = self._format_vector_for_pg(query_embedding)

        # Build query with optional specialty filter
        specialty_filter = ""
        params = {"top_k": top_k}

        if specialty:
            specialty_filter = "AND chunk_metadata->>'specialty' = :specialty"
            params["specialty"] = specialty

        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    text(f"""
                        SELECT
                            pc.id,
                            pc.content,
                            pc.chunk_metadata,
                            1 - (pc.embedding <=> '{vector_literal}'::vector) as similarity,
                            rp.title,
                            rp.source_url
                        FROM paper_chunks pc
                        JOIN research_papers rp ON pc.paper_id = rp.id
                        WHERE 1 - (pc.embedding <=> '{vector_literal}'::vector) >= {min_similarity}
                        {specialty_filter}
                        ORDER BY pc.embedding <=> '{vector_literal}'::vector
                        LIMIT :top_k
                    """),
                    params,
                )

                results = []
                for row in result:
                    results.append(
                        {
                            "id": row[0],
                            "content": row[1],
                            "metadata": json.loads(row[2]) if row[2] else {},
                            "similarity": float(row[3]),
                            "title": row[4],
                            "source_url": row[5],
                        }
                    )

                return results
        except SQLAlchemyError as e:
            print(f"Search error: {e}")
            return []

    def get_paper_count(self) -> int:
        """Get total number of papers in store."""
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM research_papers"))
                return result.fetchone()[0]
        except SQLAlchemyError:
            return 0

    def get_chunk_count(self) -> int:
        """Get total number of chunks in store."""
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM paper_chunks"))
                return result.fetchone()[0]
        except SQLAlchemyError:
            return 0

    def delete_paper(self, paper_id: str) -> bool:
        """
        Delete a paper and its chunks.

        Args:
            paper_id: Paper identifier to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    text("DELETE FROM research_papers WHERE paper_id = :paper_id"),
                    {"paper_id": paper_id},
                )
                conn.commit()
                return result.rowcount > 0
        except SQLAlchemyError as e:
            print(f"Delete error: {e}")
            return False


# Singleton instance
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get or create singleton vector store."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
