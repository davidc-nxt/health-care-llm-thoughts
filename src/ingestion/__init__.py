"""Ingestion Package - Research Paper Sources"""

from src.ingestion.arxiv_client import ArxivClient
from src.ingestion.pubmed_client import PubMedClient, ResearchPaper

__all__ = [
    "PubMedClient",
    "ArxivClient",
    "ResearchPaper",
]
