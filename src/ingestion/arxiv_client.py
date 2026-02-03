"""arXiv Research Paper Client"""

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import arxiv

from src.ingestion.pubmed_client import ResearchPaper


class ArxivClient:
    """
    Client for arXiv API for preprint access.

    Focuses on quantitative biology (q-bio) categories relevant to medicine.
    """

    # arXiv categories relevant to medical research
    MEDICAL_CATEGORIES = {
        "q-bio.BM": "Biomolecules",
        "q-bio.CB": "Cell Behavior",
        "q-bio.GN": "Genomics",
        "q-bio.MN": "Molecular Networks",
        "q-bio.NC": "Neurons and Cognition",
        "q-bio.OT": "Other Quantitative Biology",
        "q-bio.PE": "Populations and Evolution",
        "q-bio.QM": "Quantitative Methods",
        "q-bio.SC": "Subcellular Processes",
        "q-bio.TO": "Tissues and Organs",
        "cs.AI": "Artificial Intelligence (Medical AI)",
        "cs.LG": "Machine Learning",
        "stat.ML": "Machine Learning (Statistics)",
    }

    # Specialty to arXiv category mapping
    SPECIALTY_CATEGORIES = {
        "cardiology": ["q-bio.TO", "q-bio.QM"],
        "oncology": ["q-bio.CB", "q-bio.TO", "q-bio.GN"],
        "neurology": ["q-bio.NC", "q-bio.QM"],
        "genomics": ["q-bio.GN", "q-bio.MN"],
        "medical_ai": ["cs.AI", "cs.LG", "stat.ML"],
        "infectious_disease": ["q-bio.PE", "q-bio.MN"],
    }

    REQUEST_DELAY = 3.0  # arXiv recommends ~3 second delay

    def __init__(self):
        """Initialize arXiv client."""
        self._last_request_time = 0
        self._client = arxiv.Client(
            page_size=100,
            delay_seconds=self.REQUEST_DELAY,
            num_retries=3,
        )

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    def search(
        self,
        query: str,
        specialty: Optional[str] = None,
        max_results: int = 20,
        sort_by: arxiv.SortCriterion = arxiv.SortCriterion.SubmittedDate,
    ) -> list[ResearchPaper]:
        """
        Search arXiv for papers.

        Args:
            query: Search terms
            specialty: Medical specialty to focus on
            max_results: Maximum papers to return
            sort_by: Sort criterion (default: newest first)

        Returns:
            List of ResearchPaper objects
        """
        self._rate_limit()

        # Build category filter
        categories = []
        if specialty and specialty.lower() in self.SPECIALTY_CATEGORIES:
            categories = self.SPECIALTY_CATEGORIES[specialty.lower()]
        else:
            # Default to all medical-relevant categories
            categories = list(self.MEDICAL_CATEGORIES.keys())

        # Build search query
        cat_query = " OR ".join([f"cat:{cat}" for cat in categories])
        full_query = f"({query}) AND ({cat_query})"

        search = arxiv.Search(
            query=full_query,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=arxiv.SortOrder.Descending,
        )

        papers = []
        try:
            for result in self._client.results(search):
                papers.append(self._convert_to_research_paper(result, specialty))
        except Exception as e:
            print(f"arXiv search error: {e}")

        return papers

    def _convert_to_research_paper(
        self, result: arxiv.Result, specialty: Optional[str] = None
    ) -> ResearchPaper:
        """Convert arXiv result to ResearchPaper."""
        # Extract arXiv ID
        arxiv_id = result.entry_id.split("/abs/")[-1]

        return ResearchPaper(
            paper_id=f"arxiv:{arxiv_id}",
            title=result.title.replace("\n", " "),
            abstract=result.summary.replace("\n", " "),
            authors=[author.name for author in result.authors],
            source="arxiv",
            specialty=specialty or self._infer_specialty(result.categories),
            publication_date=result.published,
            source_url=result.entry_id,
            full_text=None,  # Full text requires PDF download
            doi=result.doi,
        )

    def _infer_specialty(self, categories: list[str]) -> Optional[str]:
        """Infer specialty from arXiv categories."""
        cat_set = set(categories)

        for specialty, cats in self.SPECIALTY_CATEGORIES.items():
            if cat_set & set(cats):
                return specialty

        return None

    def fetch_by_id(self, arxiv_id: str) -> Optional[ResearchPaper]:
        """
        Fetch a specific paper by arXiv ID.

        Args:
            arxiv_id: arXiv identifier (e.g., "2301.12345")

        Returns:
            ResearchPaper or None if not found
        """
        self._rate_limit()

        search = arxiv.Search(id_list=[arxiv_id])

        try:
            for result in self._client.results(search):
                return self._convert_to_research_paper(result)
        except Exception as e:
            print(f"arXiv fetch error: {e}")

        return None
