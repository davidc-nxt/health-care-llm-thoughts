"""Document Chunking for RAG Pipeline"""

from dataclasses import dataclass
from typing import Optional

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    # Fallback for older langchain versions
    from langchain.text_splitter import RecursiveCharacterTextSplitter

from src.ingestion.pubmed_client import ResearchPaper


@dataclass
class PaperChunk:
    """Represents a chunk of a research paper for embedding."""

    paper_id: str
    chunk_index: int
    content: str
    metadata: dict

    @property
    def chunk_id(self) -> str:
        """Unique identifier for this chunk."""
        return f"{self.paper_id}:chunk:{self.chunk_index}"


class DocumentChunker:
    """
    Document chunking for research papers using LangChain.

    Uses RecursiveCharacterTextSplitter to maintain semantic coherence
    by splitting on paragraph/sentence boundaries.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        separators: Optional[list[str]] = None,
    ):
        """
        Initialize chunker with configuration.

        Args:
            chunk_size: Target size of each chunk in characters
            chunk_overlap: Overlap between consecutive chunks
            separators: Custom separators (default: paragraphs, sentences, words)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        if separators is None:
            # Order matters: try paragraphs first, then sentences, then words
            separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
            length_function=len,
        )

    def chunk_paper(self, paper: ResearchPaper) -> list[PaperChunk]:
        """
        Split a research paper into chunks.

        Combines title, abstract, and full text (if available) for chunking.
        Each chunk retains metadata for filtering and citation.

        Args:
            paper: ResearchPaper to chunk

        Returns:
            List of PaperChunk objects
        """
        # Build full document text
        text_parts = []

        # Always include title
        text_parts.append(f"Title: {paper.title}")

        # Include abstract
        if paper.abstract:
            text_parts.append(f"\nAbstract: {paper.abstract}")

        # Include full text if available
        if paper.full_text:
            text_parts.append(f"\nFull Text: {paper.full_text}")

        full_text = "\n".join(text_parts)

        # Split into chunks
        text_chunks = self._splitter.split_text(full_text)

        # Build base metadata
        base_metadata = {
            "paper_id": paper.paper_id,
            "title": paper.title,
            "source": paper.source,
            "specialty": paper.specialty,
            "source_url": paper.source_url,
            "publication_date": (
                paper.publication_date.isoformat() if paper.publication_date else None
            ),
            "authors": paper.authors[:5] if paper.authors else [],  # Limit authors
        }

        # Create chunk objects
        chunks = []
        for i, text in enumerate(text_chunks):
            chunk_metadata = {
                **base_metadata,
                "chunk_index": i,
                "total_chunks": len(text_chunks),
            }

            chunks.append(
                PaperChunk(
                    paper_id=paper.paper_id,
                    chunk_index=i,
                    content=text,
                    metadata=chunk_metadata,
                )
            )

        return chunks

    def chunk_papers(self, papers: list[ResearchPaper]) -> list[PaperChunk]:
        """
        Chunk multiple papers.

        Args:
            papers: List of ResearchPaper objects

        Returns:
            List of all PaperChunk objects
        """
        all_chunks = []
        for paper in papers:
            all_chunks.extend(self.chunk_paper(paper))
        return all_chunks

    def estimate_token_count(self, text: str) -> int:
        """
        Estimate token count for text (rough approximation).

        Uses ~4 characters per token as a rough estimate.
        For precise counting, use tiktoken.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // 4
