"""PubMed/PMC Research Paper Client"""

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Generator, Optional

from Bio import Entrez

from src.config import get_settings


@dataclass
class ResearchPaper:
    """Represents a research paper from PubMed/PMC."""

    paper_id: str
    title: str
    abstract: Optional[str]
    authors: list[str]
    source: str  # 'pubmed' or 'pmc'
    specialty: Optional[str]
    publication_date: Optional[datetime]
    source_url: str
    full_text: Optional[str] = None
    mesh_terms: list[str] = None
    doi: Optional[str] = None

    def __post_init__(self):
        if self.mesh_terms is None:
            self.mesh_terms = []


class PubMedClient:
    """
    Client for PubMed and PMC APIs using Biopython.

    Implements rate limiting (3 requests/second for NCBI API)
    and specialty-based searching.
    """

    # NCBI rate limit: 3 requests per second without API key, 10 with key
    REQUEST_DELAY = 0.34  # ~3 req/sec

    # Specialty to MeSH term mappings
    SPECIALTY_MESH_TERMS = {
        "cardiology": [
            "Cardiology",
            "Heart Diseases",
            "Cardiovascular Diseases",
            "Myocardial Infarction",
            "Arrhythmias, Cardiac",
        ],
        "oncology": [
            "Oncology",
            "Neoplasms",
            "Cancer",
            "Tumor",
            "Carcinoma",
        ],
        "neurology": [
            "Neurology",
            "Nervous System Diseases",
            "Brain Diseases",
            "Stroke",
            "Alzheimer Disease",
        ],
        "pulmonology": [
            "Pulmonary Medicine",
            "Lung Diseases",
            "Respiratory Tract Diseases",
            "Asthma",
            "COPD",
        ],
        "endocrinology": [
            "Endocrinology",
            "Diabetes Mellitus",
            "Thyroid Diseases",
            "Metabolic Diseases",
        ],
        "infectious_disease": [
            "Communicable Diseases",
            "Infection",
            "Viral Diseases",
            "Bacterial Infections",
        ],
        "gastroenterology": [
            "Gastroenterology",
            "Digestive System Diseases",
            "Liver Diseases",
            "Inflammatory Bowel Diseases",
        ],
    }

    def __init__(self, email: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize PubMed client.

        Args:
            email: Required email for NCBI API access
            api_key: Optional NCBI API key for higher rate limits
        """
        settings = get_settings()
        self.email = email or settings.ncbi_email
        self.api_key = api_key or settings.ncbi_api_key

        if not self.email:
            raise ValueError(
                "NCBI requires an email address. Set NCBI_EMAIL in your environment."
            )

        Entrez.email = self.email
        if self.api_key:
            Entrez.api_key = self.api_key
            self.REQUEST_DELAY = 0.1  # 10 req/sec with API key

        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    def search(
        self,
        query: str,
        specialty: Optional[str] = None,
        max_results: int = 20,
        days_back: int = 365,
        open_access_only: bool = True,
    ) -> list[str]:
        """
        Search PubMed for articles matching query.

        Args:
            query: Search terms
            specialty: Medical specialty for focused results
            max_results: Maximum papers to return
            days_back: Limit to papers published within N days
            open_access_only: Only return open access papers

        Returns:
            List of PubMed IDs
        """
        self._rate_limit()

        # Build search query
        search_terms = [query]

        if specialty and specialty.lower() in self.SPECIALTY_MESH_TERMS:
            mesh_terms = self.SPECIALTY_MESH_TERMS[specialty.lower()]
            mesh_query = " OR ".join([f'"{term}"[MeSH]' for term in mesh_terms])
            search_terms.append(f"({mesh_query})")

        if open_access_only:
            search_terms.append('"open access"[filter]')

        # Date filter
        if days_back:
            search_terms.append(f'"{days_back}"[PDAT]')

        full_query = " AND ".join(search_terms)

        try:
            handle = Entrez.esearch(
                db="pubmed",
                term=full_query,
                retmax=max_results,
                sort="relevance",
                usehistory="y",
            )
            results = Entrez.read(handle)
            handle.close()
            return results.get("IdList", [])
        except Exception as e:
            print(f"PubMed search error: {e}")
            return []

    def fetch_papers(self, pmids: list[str]) -> Generator[ResearchPaper, None, None]:
        """
        Fetch paper details for given PubMed IDs.

        Args:
            pmids: List of PubMed IDs

        Yields:
            ResearchPaper objects
        """
        if not pmids:
            return

        self._rate_limit()

        try:
            handle = Entrez.efetch(
                db="pubmed",
                id=",".join(pmids),
                rettype="xml",
                retmode="xml",
            )
            records = Entrez.read(handle)
            handle.close()

            for article in records.get("PubmedArticle", []):
                yield self._parse_pubmed_article(article)

        except Exception as e:
            print(f"PubMed fetch error: {e}")

    def _parse_pubmed_article(self, article: dict) -> ResearchPaper:
        """Parse a PubMed article record into ResearchPaper."""
        medline = article.get("MedlineCitation", {})
        article_data = medline.get("Article", {})

        # Extract PMID
        pmid = str(medline.get("PMID", ""))

        # Title
        title = article_data.get("ArticleTitle", "Untitled")

        # Abstract
        abstract_parts = article_data.get("Abstract", {}).get("AbstractText", [])
        if isinstance(abstract_parts, list):
            abstract = " ".join(
                [
                    str(part.attributes.get("Label", "") + ": " + str(part))
                    if hasattr(part, "attributes")
                    else str(part)
                    for part in abstract_parts
                ]
            )
        else:
            abstract = str(abstract_parts) if abstract_parts else None

        # Authors
        author_list = article_data.get("AuthorList", [])
        authors = []
        for author in author_list:
            if isinstance(author, dict):
                last = author.get("LastName", "")
                first = author.get("ForeName", "")
                if last:
                    authors.append(f"{last}, {first}".strip(", "))

        # Publication date
        pub_date = None
        journal_info = article_data.get("Journal", {}).get("JournalIssue", {})
        pub_date_dict = journal_info.get("PubDate", {})
        if pub_date_dict:
            year = pub_date_dict.get("Year")
            month = pub_date_dict.get("Month", "01")
            day = pub_date_dict.get("Day", "01")
            if year:
                try:
                    # Handle month names
                    month_map = {
                        "Jan": "01",
                        "Feb": "02",
                        "Mar": "03",
                        "Apr": "04",
                        "May": "05",
                        "Jun": "06",
                        "Jul": "07",
                        "Aug": "08",
                        "Sep": "09",
                        "Oct": "10",
                        "Nov": "11",
                        "Dec": "12",
                    }
                    month = month_map.get(month, month)
                    pub_date = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
                except ValueError:
                    pub_date = datetime.strptime(f"{year}-01-01", "%Y-%m-%d")

        # MeSH terms
        mesh_list = medline.get("MeshHeadingList", [])
        mesh_terms = []
        for mesh in mesh_list:
            if isinstance(mesh, dict):
                descriptor = mesh.get("DescriptorName")
                if descriptor:
                    mesh_terms.append(str(descriptor))

        # DOI
        doi = None
        article_ids = article.get("PubmedData", {}).get("ArticleIdList", [])
        for aid in article_ids:
            if hasattr(aid, "attributes") and aid.attributes.get("IdType") == "doi":
                doi = str(aid)
                break

        return ResearchPaper(
            paper_id=f"pubmed:{pmid}",
            title=title,
            abstract=abstract,
            authors=authors,
            source="pubmed",
            specialty=self._infer_specialty(mesh_terms),
            publication_date=pub_date,
            source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            mesh_terms=mesh_terms,
            doi=doi,
        )

    def _infer_specialty(self, mesh_terms: list[str]) -> Optional[str]:
        """Infer medical specialty from MeSH terms."""
        mesh_set = set(term.lower() for term in mesh_terms)

        for specialty, terms in self.SPECIALTY_MESH_TERMS.items():
            term_set = set(t.lower() for t in terms)
            if mesh_set & term_set:
                return specialty

        return None

    def search_and_fetch(
        self,
        query: str,
        specialty: Optional[str] = None,
        max_results: int = 10,
        **search_kwargs,
    ) -> list[ResearchPaper]:
        """
        Convenience method to search and fetch in one call.

        Args:
            query: Search terms
            specialty: Medical specialty
            max_results: Maximum papers to return
            **search_kwargs: Additional arguments for search()

        Returns:
            List of ResearchPaper objects
        """
        pmids = self.search(
            query=query,
            specialty=specialty,
            max_results=max_results,
            **search_kwargs,
        )
        return list(self.fetch_papers(pmids))
