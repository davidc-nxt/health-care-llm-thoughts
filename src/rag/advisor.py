"""Medical Research Advisor using RAG"""

from typing import Optional

import httpx

from src.config import get_settings
from src.rag.vector_store import VectorStore, get_vector_store
from src.security.audit_logger import log_action


class MedicalAdvisor:
    """
    LLM-powered medical research advisor.

    Uses RAG to provide research-backed insights for patient care.
    All queries are audit logged for HIPAA compliance.
    """

    SYSTEM_PROMPT = """You are a medical research assistant helping healthcare professionals 
find relevant research for patient care decisions. You have access to recent medical literature.

Your role is to:
1. Analyze the provided research context
2. Identify relevant findings for the clinical question
3. Provide evidence-based insights with citations
4. Highlight any conflicting findings or limitations
5. Always recommend consulting with specialists for complex cases

Format your response with:
- **Key Findings**: Summarize the most relevant research
- **Evidence Level**: Indicate strength of evidence (Strong/Moderate/Limited)
- **Clinical Implications**: Practical takeaways for patient care
- **Citations**: Reference the source papers

IMPORTANT: You are providing research support, not clinical recommendations. 
Final treatment decisions must be made by qualified healthcare providers."""

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize medical advisor.

        Args:
            vector_store: Vector store for retrieval
            api_key: OpenRouter API key
            model: LLM model to use
        """
        settings = get_settings()
        self._vector_store = vector_store or get_vector_store()
        self._api_key = api_key or settings.openrouter_api_key
        self._model = model or settings.openrouter_model
        self._base_url = settings.openrouter_base_url

        if not self._api_key:
            raise ValueError(
                "OpenRouter API key is required. Set OPENROUTER_API_KEY in your environment."
            )

    def _retrieve_context(
        self, query: str, specialty: Optional[str] = None, top_k: int = 5
    ) -> list[dict]:
        """Retrieve relevant research context."""
        return self._vector_store.search(
            query=query, specialty=specialty, top_k=top_k, min_similarity=0.3
        )

    def _build_context_prompt(self, results: list[dict]) -> str:
        """Build context section from search results."""
        if not results:
            return "No relevant research papers found in the knowledge base."

        context_parts = ["## Research Context\n"]

        for i, result in enumerate(results, 1):
            context_parts.append(f"### Source {i}: {result['title']}")
            context_parts.append(f"**Relevance Score**: {result['similarity']:.2%}")
            context_parts.append(f"**Content**: {result['content']}")
            context_parts.append(f"**URL**: {result['source_url']}\n")

        return "\n".join(context_parts)

    def advise(
        self,
        query: str,
        specialty: Optional[str] = None,
        patient_context: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> dict:
        """
        Generate research-backed advice for a clinical question.

        Args:
            query: Clinical question or topic
            specialty: Medical specialty for focused results
            patient_context: De-identified patient context (optional)
            user_id: User ID for audit logging

        Returns:
            Dict with advice, sources, and metadata
        """
        # Audit log the query
        log_action(
            action="GENERATE_ADVICE",
            user_id=user_id,
            resource_type="research_query",
            request_details={
                "query": query,
                "specialty": specialty,
                "has_patient_context": patient_context is not None,
            },
            phi_accessed=patient_context is not None,
        )

        # Retrieve relevant research
        search_results = self._retrieve_context(query, specialty)

        # Build the full prompt
        context_section = self._build_context_prompt(search_results)

        user_message_parts = [context_section, f"\n## Clinical Question\n{query}"]

        if patient_context:
            user_message_parts.append(
                f"\n## Patient Context (De-identified)\n{patient_context}"
            )

        user_message = "\n".join(user_message_parts)

        # Call LLM
        try:
            response = self._call_llm(user_message)

            return {
                "advice": response,
                "sources": [
                    {
                        "title": r["title"],
                        "url": r["source_url"],
                        "similarity": r["similarity"],
                    }
                    for r in search_results
                ],
                "specialty": specialty,
                "model": self._model,
                "source_count": len(search_results),
            }
        except Exception as e:
            return {
                "advice": None,
                "error": str(e),
                "sources": [],
                "specialty": specialty,
            }

    def _call_llm(self, user_message: str) -> str:
        """Call OpenRouter LLM API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://clinic-ai-llm.local",
            "X-Title": "Medical AI Research Assistant",
        }

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.3,  # Lower temperature for factual accuracy
            "max_tokens": 2000,
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            return data["choices"][0]["message"]["content"]

    def search_only(
        self, query: str, specialty: Optional[str] = None, top_k: int = 10
    ) -> list[dict]:
        """
        Search without LLM generation (for quick lookups).

        Args:
            query: Search query
            specialty: Filter by specialty
            top_k: Number of results

        Returns:
            List of search results
        """
        return self._retrieve_context(query, specialty, top_k)


# Singleton instance
_advisor: Optional[MedicalAdvisor] = None


def get_advisor() -> MedicalAdvisor:
    """Get or create singleton medical advisor."""
    global _advisor
    if _advisor is None:
        _advisor = MedicalAdvisor()
    return _advisor
