"""Medical AI LLM CLI Interface"""

import json
import sys
from typing import Optional

import click

from src.config import get_settings


@click.group()
@click.version_option(version="0.1.0", prog_name="clinic-ai")
def cli():
    """Medical AI LLM - Research-powered clinical decision support."""
    pass


@cli.command()
def status():
    """Check system status and database connectivity."""
    from sqlalchemy import create_engine, text

    settings = get_settings()
    click.echo("🏥 Medical AI LLM System Status\n")

    # Check database
    try:
        engine = create_engine(settings.database_url_sync)
        with engine.connect() as conn:
            # Check pgvector extension
            result = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
            row = result.fetchone()
            if row:
                click.echo(f"✅ PostgreSQL connected (pgvector v{row[0]})")
            else:
                click.echo("⚠️  PostgreSQL connected but pgvector not installed")

            # Check paper counts
            paper_count = conn.execute(
                text("SELECT COUNT(*) FROM research_papers")
            ).fetchone()[0]
            chunk_count = conn.execute(
                text("SELECT COUNT(*) FROM paper_chunks")
            ).fetchone()[0]
            click.echo(f"📚 Papers indexed: {paper_count}")
            click.echo(f"📄 Chunks stored: {chunk_count}")

    except Exception as e:
        click.echo(f"❌ Database error: {e}", err=True)
        sys.exit(1)

    # Check LLM configuration
    if settings.openrouter_api_key:
        click.echo(f"🤖 LLM configured: {settings.openrouter_model}")
    else:
        click.echo("⚠️  LLM not configured (set OPENROUTER_API_KEY)")

    # Check NCBI configuration
    if settings.ncbi_email:
        click.echo(f"🔬 PubMed configured: {settings.ncbi_email}")
    else:
        click.echo("⚠️  PubMed not configured (set NCBI_EMAIL)")

    click.echo("\n✨ System ready!")


@cli.command("ingest-papers")
@click.option(
    "--specialty",
    "-s",
    type=str,
    required=True,
    help="Medical specialty (e.g., cardiology, oncology, neurology)",
)
@click.option(
    "--query",
    "-q",
    type=str,
    default=None,
    help="Additional search terms",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=10,
    help="Maximum papers to fetch",
)
@click.option(
    "--source",
    type=click.Choice(["pubmed", "arxiv", "both"]),
    default="both",
    help="Paper source",
)
@click.option(
    "--days",
    type=int,
    default=365,
    help="Papers from last N days",
)
def ingest_papers(specialty: str, query: Optional[str], limit: int, source: str, days: int):
    """Fetch and index research papers by specialty."""
    from src.ingestion import ArxivClient, PubMedClient
    from src.rag import DocumentChunker, get_vector_store

    click.echo(f"🔍 Searching for {specialty} papers...")

    papers = []
    search_query = query or f"{specialty} treatment guidelines recent advances"

    # Fetch from PubMed
    if source in ("pubmed", "both"):
        try:
            pubmed = PubMedClient()
            click.echo(f"📚 Searching PubMed for: {search_query}")
            pubmed_papers = pubmed.search_and_fetch(
                query=search_query,
                specialty=specialty,
                max_results=limit,
                days_back=days,
            )
            papers.extend(pubmed_papers)
            click.echo(f"   Found {len(pubmed_papers)} PubMed papers")
        except Exception as e:
            click.echo(f"⚠️  PubMed error: {e}", err=True)

    # Fetch from arXiv
    if source in ("arxiv", "both"):
        try:
            arxiv = ArxivClient()
            click.echo(f"📄 Searching arXiv for: {search_query}")
            arxiv_papers = arxiv.search(
                query=search_query,
                specialty=specialty,
                max_results=limit,
            )
            papers.extend(arxiv_papers)
            click.echo(f"   Found {len(arxiv_papers)} arXiv papers")
        except Exception as e:
            click.echo(f"⚠️  arXiv error: {e}", err=True)

    if not papers:
        click.echo("❌ No papers found", err=True)
        sys.exit(1)

    # Chunk and index
    click.echo(f"\n📊 Indexing {len(papers)} papers...")
    chunker = DocumentChunker()
    vector_store = get_vector_store()

    indexed = 0
    with click.progressbar(papers, label="Indexing") as bar:
        for paper in bar:
            try:
                # Store paper
                paper_db_id = vector_store.store_paper(
                    paper_id=paper.paper_id,
                    title=paper.title,
                    abstract=paper.abstract,
                    authors=paper.authors,
                    source=paper.source,
                    specialty=paper.specialty or specialty,
                    publication_date=paper.publication_date,
                    source_url=paper.source_url,
                )

                # Chunk and store embeddings
                chunks = chunker.chunk_paper(paper)
                vector_store.store_chunks(chunks, paper_db_id)
                indexed += 1

            except Exception as e:
                click.echo(f"\n⚠️  Error indexing {paper.title[:50]}...: {e}", err=True)

    click.echo(f"\n✅ Indexed {indexed}/{len(papers)} papers successfully!")


@cli.command("search")
@click.argument("query")
@click.option(
    "--specialty",
    "-s",
    type=str,
    default=None,
    help="Filter by specialty",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=10,
    help="Number of results",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON",
)
def search(query: str, specialty: Optional[str], limit: int, output_json: bool):
    """Semantic search across indexed papers."""
    from src.rag import get_vector_store

    vector_store = get_vector_store()
    results = vector_store.search(query, specialty=specialty, top_k=limit)

    if output_json:
        click.echo(json.dumps(results, indent=2, default=str))
        return

    if not results:
        click.echo("No matching papers found.")
        return

    click.echo(f"\n🔍 Found {len(results)} relevant papers:\n")

    for i, result in enumerate(results, 1):
        similarity = result["similarity"]
        title = result["title"]
        url = result["source_url"]
        content = result["content"][:200] + "..." if len(result["content"]) > 200 else result["content"]

        click.echo(f"{i}. [{similarity:.1%}] {title}")
        click.echo(f"   URL: {url}")
        click.echo(f"   Preview: {content}\n")


@cli.command("advise")
@click.argument("query")
@click.option(
    "--specialty",
    "-s",
    type=str,
    default=None,
    help="Medical specialty context",
)
@click.option(
    "--patient-context",
    "-p",
    type=str,
    default=None,
    help="De-identified patient context",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON",
)
def advise(query: str, specialty: Optional[str], patient_context: Optional[str], output_json: bool):
    """Get research-backed medical advice."""
    from src.rag import get_advisor

    click.echo("🤔 Analyzing research and generating advice...\n")

    try:
        advisor = get_advisor()
        result = advisor.advise(
            query=query,
            specialty=specialty,
            patient_context=patient_context,
        )

        if output_json:
            click.echo(json.dumps(result, indent=2, default=str))
            return

        if result.get("error"):
            click.echo(f"❌ Error: {result['error']}", err=True)
            sys.exit(1)

        click.echo("📋 MEDICAL RESEARCH ANALYSIS\n")
        click.echo("=" * 60)
        click.echo(result["advice"])
        click.echo("=" * 60)

        click.echo(f"\n📚 Sources ({len(result['sources'])}):")
        for src in result["sources"]:
            click.echo(f"   • [{src['similarity']:.1%}] {src['title']}")
            click.echo(f"     {src['url']}")

    except ValueError as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        click.echo("   Set OPENROUTER_API_KEY in your .env file")
        sys.exit(1)


@cli.command("test-fhir")
@click.option("--sandbox", is_flag=True, help="Use Epic sandbox")
@click.option("--patient-id", type=str, default="erXuFYUfucBZaryVksYEcMg3", help="Test patient ID")
def test_fhir(sandbox: bool, patient_id: str):
    """Test FHIR connection (Epic sandbox)."""
    from src.ehr import EpicIntegration

    click.echo("🏥 Testing Epic FHIR connection...\n")

    epic = EpicIntegration(use_sandbox=sandbox)
    status = epic.test_connection()

    if status["status"] == "connected":
        click.echo(f"✅ Connected to Epic FHIR")
        click.echo(f"   FHIR Version: {status.get('fhir_version')}")
        click.echo(f"   Software: {status.get('software')}")
    else:
        click.echo(f"❌ Connection failed: {status.get('message')}")


@cli.command("generate-key")
def generate_key():
    """Generate a new encryption key for HIPAA compliance."""
    from src.security import EncryptionService

    key = EncryptionService.generate_key()
    click.echo("🔐 Generated new Fernet encryption key:\n")
    click.echo(f"   {key}")
    click.echo("\nAdd this to your .env file as ENCRYPTION_KEY")


if __name__ == "__main__":
    cli()
