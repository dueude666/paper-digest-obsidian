"""Typer CLI entrypoints."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from paper_digest.config import AppSettings
from paper_digest.http import ResilientHttpClient
from paper_digest.knowledge.notes_index import NoteIndexService
from paper_digest.logging import configure_logging
from paper_digest.models import DoctorCheck
from paper_digest.obsidian_writer.reindexer import ObsidianReindexer
from paper_digest.obsidian_writer.writer import ObsidianWriter
from paper_digest.paper_fetcher.cache import CacheManager
from paper_digest.paper_fetcher.fetcher import PaperFetcher
from paper_digest.paper_images.extractor import PaperImageExtractor
from paper_digest.paper_parser.pdf_parser import PDFParser
from paper_digest.paper_sources.arxiv import ArxivSource
from paper_digest.paper_sources.openalex import OpenAlexSource
from paper_digest.paper_sources.semantic_scholar import SemanticScholarSource
from paper_digest.recommendation.daily import DailyRecommendationService
from paper_digest.research.profile import ResearchProfileLoader
from paper_digest.services.workflow import PaperWorkflowService
from paper_digest.summarizer.heuristic import HeuristicSummarizer
from paper_digest.summarizer.llm import OpenAICompatibleSummarizer

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Paper digest tools for Obsidian.",
)


@dataclass
class Runtime:
    settings: AppSettings
    http_client: ResilientHttpClient
    fetcher: PaperFetcher
    workflow: PaperWorkflowService
    writer: ObsidianWriter
    arxiv_source: ArxivSource
    semantic_source: SemanticScholarSource
    note_index_service: NoteIndexService
    profile_loader: ResearchProfileLoader
    daily_service: DailyRecommendationService
    image_extractor: PaperImageExtractor

    def close(self) -> None:
        self.http_client.close()


def build_runtime(*, verbose: bool = False) -> Runtime:
    settings = AppSettings()
    configure_logging(verbose=verbose, level=settings.log_level)
    http_client = ResilientHttpClient(settings=settings)
    cache = CacheManager(root=settings.cache_dir)
    arxiv_source = ArxivSource(http_client=http_client, settings=settings)
    semantic_source = SemanticScholarSource(http_client=http_client, settings=settings)
    fetcher = PaperFetcher(
        sources=[arxiv_source, semantic_source, OpenAlexSource()],
        cache=cache,
        http_client=http_client,
    )
    parser = PDFParser(cache=cache)
    summarizer = (
        OpenAICompatibleSummarizer(settings=settings, http_client=http_client)
        if settings.summary_backend == "openai-compatible"
        else HeuristicSummarizer()
    )
    writer = ObsidianWriter(settings=settings)
    note_index_service = NoteIndexService()
    profile_loader = ResearchProfileLoader()
    image_extractor = PaperImageExtractor(http_client=http_client)
    workflow = PaperWorkflowService(
        settings=settings,
        fetcher=fetcher,
        parser=parser,
        summarizer=summarizer,
        writer=writer,
        image_extractor=image_extractor,
    )
    daily_service = DailyRecommendationService(
        settings=settings,
        arxiv_source=arxiv_source,
        semantic_source=semantic_source,
        workflow=workflow,
        writer=writer,
        note_index_service=note_index_service,
        profile_loader=profile_loader,
    )
    return Runtime(
        settings=settings,
        http_client=http_client,
        fetcher=fetcher,
        workflow=workflow,
        writer=writer,
        arxiv_source=arxiv_source,
        semantic_source=semantic_source,
        note_index_service=note_index_service,
        profile_loader=profile_loader,
        daily_service=daily_service,
        image_extractor=image_extractor,
    )


@app.command("summarize-paper")
def summarize_paper_command(
    url_or_id: Annotated[str | None, typer.Argument(help="arXiv URL or arXiv identifier.")] = None,
    title: Annotated[str | None, typer.Option("--title", help="Paper title to search.")] = None,
    topic: Annotated[str | None, typer.Option("--topic", help="Output topic folder name.")] = None,
    vault: Annotated[Path | None, typer.Option("--vault", help="Obsidian vault path.")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Generate output without writing files.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Refresh cache and re-download artifacts.")
    ] = False,
    extract_images: Annotated[
        bool,
        typer.Option(
            "--extract-images/--no-extract-images",
            help="Extract paper images into the image assets folder.",
        ),
    ] = False,
    overwrite: Annotated[
        str | None,
        typer.Option("--overwrite", help="Conflict strategy: overwrite, skip, suffix."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable debug logging.")] = False,
) -> None:
    _summarize_paper(
        url_or_id=url_or_id,
        title=title,
        topic=topic,
        vault=vault,
        dry_run=dry_run,
        force=force,
        overwrite=overwrite,
        verbose=verbose,
        extract_images=extract_images,
    )


@app.command("summarize-topic")
def summarize_topic_command(
    query: Annotated[
        str, typer.Argument(help="Topic query, for example 'retrieval augmented generation'.")
    ],
    limit: Annotated[
        int, typer.Option("--limit", min=1, max=50, help="Number of papers to summarize.")
    ] = 10,
    topic: Annotated[str | None, typer.Option("--topic", help="Output topic folder name.")] = None,
    vault: Annotated[Path | None, typer.Option("--vault", help="Obsidian vault path.")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Generate output without writing files.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Refresh cache and re-download artifacts.")
    ] = False,
    extract_images: Annotated[
        bool,
        typer.Option(
            "--extract-images/--no-extract-images",
            help="Extract paper images for each generated note.",
        ),
    ] = False,
    overwrite: Annotated[
        str | None,
        typer.Option("--overwrite", help="Conflict strategy: overwrite, skip, suffix."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable debug logging.")] = False,
) -> None:
    _summarize_topic(
        query=query,
        limit=limit,
        topic=topic,
        vault=vault,
        dry_run=dry_run,
        force=force,
        overwrite=overwrite,
        verbose=verbose,
        extract_images=extract_images,
    )


@app.command("recommend-daily")
def recommend_daily_command(
    profile: Annotated[
        Path | None,
        typer.Option("--profile", help="Research profile YAML path."),
    ] = None,
    top_n: Annotated[
        int,
        typer.Option("--top-n", min=1, max=30, help="Number of daily recommendations."),
    ] = 10,
    analyze_top_n: Annotated[
        int,
        typer.Option(
            "--analyze-top-n", min=0, max=10, help="How many top papers to fully analyze."
        ),
    ] = 3,
    vault: Annotated[Path | None, typer.Option("--vault", help="Obsidian vault path.")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Generate output without writing files.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Refresh cache and regenerate notes.")
    ] = False,
    overwrite: Annotated[
        str | None,
        typer.Option("--overwrite", help="Conflict strategy: overwrite, skip, suffix."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable debug logging.")] = False,
) -> None:
    runtime = build_runtime(verbose=verbose)
    try:
        profile_path = runtime.settings.resolved_research_profile_path(override=profile)
        if profile_path is None:
            raise typer.BadParameter(
                "Research profile is required. Use --profile or RESEARCH_PROFILE_PATH."
            )
        digest, results = runtime.daily_service.recommend(
            profile_path=profile_path,
            top_n=top_n,
            analyze_top_n=analyze_top_n,
            vault_override=vault,
            dry_run=dry_run,
            force=force,
            overwrite_strategy=overwrite,
        )
        typer.echo(results[0].relative_path)
        typer.echo(f"papers={len(digest.recommended_papers)}")
        typer.echo(digest.overview)
    finally:
        runtime.close()


@app.command("search-notes")
def search_notes_command(
    query: Annotated[str, typer.Argument(help="Search query for existing notes.")],
    limit: Annotated[
        int, typer.Option("--limit", min=1, max=30, help="Maximum results to return.")
    ] = 10,
    vault: Annotated[Path | None, typer.Option("--vault", help="Obsidian vault path.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable debug logging.")] = False,
) -> None:
    runtime = build_runtime(verbose=verbose)
    try:
        vault_root = runtime.settings.vault_path(override=vault)
        if vault_root is None:
            raise typer.BadParameter("Vault path is required. Use --vault or OBSIDIAN_VAULT_PATH.")
        note_index = runtime.note_index_service.build(
            vault_root=vault_root, include_root=vault_root
        )
        results = runtime.note_index_service.search(note_index=note_index, query=query, limit=limit)
        for result in results:
            typer.echo(f"{result.score:.1f}\t{result.path}\t{', '.join(result.matched_terms)}")
        if not results:
            typer.echo("No matching notes found.")
    finally:
        runtime.close()


@app.command("extract-images")
def extract_images_command(
    url_or_id: Annotated[str | None, typer.Argument(help="arXiv URL or arXiv identifier.")] = None,
    title: Annotated[str | None, typer.Option("--title", help="Paper title to search.")] = None,
    topic: Annotated[
        str | None, typer.Option("--topic", help="Topic folder for image assets.")
    ] = None,
    vault: Annotated[Path | None, typer.Option("--vault", help="Obsidian vault path.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable debug logging.")] = False,
) -> None:
    if bool(url_or_id) == bool(title):
        raise typer.BadParameter("Provide either a URL/arXiv id argument or --title.")

    runtime = build_runtime(verbose=verbose)
    try:
        metadata = runtime.workflow.resolve_single_metadata(
            url_or_id=url_or_id,
            title=title,
            force=False,
        )
        pdf_path = runtime.fetcher.download_pdf(metadata=metadata, force=False)
        temp_summary, _ = runtime.workflow.build_summary(
            metadata=metadata,
            force=False,
        )
        resolved_topic = topic or runtime.settings.default_topic
        topic_slug = runtime.writer.topic_slug(resolved_topic)
        paper_slug = runtime.writer.paper_slug(temp_summary)
        topic_root = runtime.writer.topic_root(
            topic_slug=topic_slug,
            vault_override=vault,
            dry_run=False,
        )
        result = runtime.image_extractor.extract(
            metadata=metadata,
            pdf_path=pdf_path,
            output_dir=topic_root / runtime.settings.assets_dir_name / paper_slug,
        )
        typer.echo(f"images={len(result.assets)}")
        if result.index_path is not None:
            typer.echo(runtime.writer.relative_path(result.index_path, vault_override=vault))
    finally:
        runtime.close()


@app.command("reindex")
def reindex_command(
    topic: Annotated[
        str | None, typer.Option("--topic", help="Topic folder name to rebuild.")
    ] = None,
    vault: Annotated[Path | None, typer.Option("--vault", help="Obsidian vault path.")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Generate output without writing files.")
    ] = False,
    overwrite: Annotated[
        str | None,
        typer.Option("--overwrite", help="Conflict strategy: overwrite, skip, suffix."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable debug logging.")] = False,
) -> None:
    settings = AppSettings()
    configure_logging(verbose=verbose, level=settings.log_level)
    writer = ObsidianWriter(settings=settings)
    reindexer = ObsidianReindexer(writer=writer)

    vault_root = settings.vault_path(override=vault)
    if vault_root is None:
        raise typer.BadParameter("Vault path is required. Use --vault or OBSIDIAN_VAULT_PATH.")

    literature_root = vault_root / settings.literature_dir_name
    topic_dirs = (
        [literature_root / topic]
        if topic
        else [path for path in literature_root.iterdir() if path.is_dir()]
    )
    for topic_dir in topic_dirs:
        result = reindexer.rebuild_topic(
            topic_dir=topic_dir,
            topic_name=topic_dir.name,
            dry_run=dry_run,
            overwrite_strategy=overwrite,
            vault_override=vault,
        )
        typer.echo(f"[reindex] {result.relative_path}")


@app.command("doctor")
def doctor_command(
    vault: Annotated[Path | None, typer.Option("--vault", help="Obsidian vault path.")] = None,
    profile: Annotated[
        Path | None, typer.Option("--profile", help="Research profile path.")
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable debug logging.")] = False,
) -> None:
    settings = AppSettings()
    configure_logging(verbose=verbose, level=settings.log_level)
    checks = _run_doctor_checks(settings=settings, vault_override=vault, profile_override=profile)
    failed = False
    for check in checks:
        status = "OK" if check.ok else "FAIL"
        typer.echo(f"[{status}] {check.name}: {check.detail}")
        failed = failed or not check.ok
    if failed:
        raise typer.Exit(code=1)


def summarize_paper_entry(
    url_or_id: Annotated[str | None, typer.Argument(help="arXiv URL or arXiv identifier.")] = None,
    title: Annotated[str | None, typer.Option("--title", help="Paper title to search.")] = None,
    topic: Annotated[str | None, typer.Option("--topic", help="Output topic folder name.")] = None,
    vault: Annotated[Path | None, typer.Option("--vault", help="Obsidian vault path.")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Generate output without writing files.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Refresh cache and re-download artifacts.")
    ] = False,
    extract_images: Annotated[
        bool,
        typer.Option("--extract-images/--no-extract-images"),
    ] = False,
    overwrite: Annotated[str | None, typer.Option("--overwrite")] = None,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
) -> None:
    _summarize_paper(
        url_or_id=url_or_id,
        title=title,
        topic=topic,
        vault=vault,
        dry_run=dry_run,
        force=force,
        overwrite=overwrite,
        verbose=verbose,
        extract_images=extract_images,
    )


def summarize_topic_entry(
    query: Annotated[str, typer.Argument(help="Topic query.")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=50)] = 10,
    topic: Annotated[str | None, typer.Option("--topic")] = None,
    vault: Annotated[Path | None, typer.Option("--vault")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    force: Annotated[bool, typer.Option("--force")] = False,
    extract_images: Annotated[bool, typer.Option("--extract-images/--no-extract-images")] = False,
    overwrite: Annotated[str | None, typer.Option("--overwrite")] = None,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
) -> None:
    _summarize_topic(
        query=query,
        limit=limit,
        topic=topic,
        vault=vault,
        dry_run=dry_run,
        force=force,
        overwrite=overwrite,
        verbose=verbose,
        extract_images=extract_images,
    )


def _summarize_paper(
    *,
    url_or_id: str | None,
    title: str | None,
    topic: str | None,
    vault: Path | None,
    dry_run: bool,
    force: bool,
    overwrite: str | None,
    verbose: bool,
    extract_images: bool,
) -> None:
    if bool(url_or_id) == bool(title):
        raise typer.BadParameter("Provide either a URL/arXiv id argument or --title.")

    runtime = build_runtime(verbose=verbose)
    try:
        note_index = _build_note_index(runtime=runtime, vault=vault)
        summary, result = runtime.workflow.summarize_paper(
            url_or_id=url_or_id,
            title=title,
            topic=topic,
            dry_run=dry_run,
            force=force,
            overwrite_strategy=overwrite,
            vault_override=vault,
            note_index=note_index,
            extract_images=extract_images,
        )
        typer.echo(result.relative_path)
        typer.echo(summary.one_sentence)
    finally:
        runtime.close()


def _summarize_topic(
    *,
    query: str,
    limit: int,
    topic: str | None,
    vault: Path | None,
    dry_run: bool,
    force: bool,
    overwrite: str | None,
    verbose: bool,
    extract_images: bool,
) -> None:
    runtime = build_runtime(verbose=verbose)
    try:
        note_index = _build_note_index(runtime=runtime, vault=vault)
        topic_summary, note_results, index_result = runtime.workflow.summarize_topic(
            query=query,
            limit=limit,
            topic=topic,
            dry_run=dry_run,
            force=force,
            overwrite_strategy=overwrite,
            vault_override=vault,
            note_index=note_index,
            extract_images=extract_images,
        )
        typer.echo(index_result.relative_path)
        typer.echo(f"papers={len(note_results)}")
        typer.echo(topic_summary.overview)
    finally:
        runtime.close()


def _build_note_index(*, runtime: Runtime, vault: Path | None):
    vault_root = runtime.settings.vault_path(override=vault)
    if vault_root is None or not vault_root.exists():
        return None
    return runtime.note_index_service.build(vault_root=vault_root, include_root=vault_root)


def _run_doctor_checks(
    *,
    settings: AppSettings,
    vault_override: Path | None,
    profile_override: Path | None,
) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    vault_path = settings.vault_path(override=vault_override)
    profile_path = settings.resolved_research_profile_path(override=profile_override)
    checks.append(
        DoctorCheck(
            name="vault_path",
            ok=vault_path is not None,
            detail=str(vault_path or "Not configured"),
        )
    )
    if vault_path is not None:
        checks.append(
            DoctorCheck(
                name="vault_exists",
                ok=vault_path.exists(),
                detail=(
                    "Vault directory exists."
                    if vault_path.exists()
                    else "Vault directory does not exist yet."
                ),
            )
        )
    checks.append(
        DoctorCheck(
            name="research_profile",
            ok=profile_path is not None and profile_path.exists(),
            detail=str(profile_path or "Not configured"),
        )
    )
    checks.append(DoctorCheck(name="cache_dir", ok=True, detail=str(settings.cache_dir)))
    for module_name in ["fitz", "pdfplumber", "httpx", "bs4", "jinja2", "yaml"]:
        try:
            importlib.import_module(module_name)
            checks.append(
                DoctorCheck(name=f"dependency:{module_name}", ok=True, detail="import ok")
            )
        except Exception as error:
            checks.append(
                DoctorCheck(name=f"dependency:{module_name}", ok=False, detail=str(error))
            )
    checks.append(
        DoctorCheck(
            name="summary_backend",
            ok=settings.summary_backend in {"heuristic", "openai-compatible"},
            detail=settings.summary_backend,
        )
    )
    return checks


def main() -> None:
    app()


def run_summarize_paper() -> None:
    typer.run(summarize_paper_entry)


def run_summarize_topic() -> None:
    typer.run(summarize_topic_entry)


def run_recommend_daily() -> None:
    typer.run(recommend_daily_command)


def run_search_notes() -> None:
    typer.run(search_notes_command)


def run_extract_images() -> None:
    typer.run(extract_images_command)
