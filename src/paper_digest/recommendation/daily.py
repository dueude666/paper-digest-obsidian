"""Daily paper recommendation workflow."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from paper_digest.config import AppSettings
from paper_digest.knowledge.notes_index import NoteIndexService
from paper_digest.models import DailyDigest, NoteIndex, PaperMetadata, RecommendedPaper, WriteResult
from paper_digest.obsidian_writer.writer import ObsidianWriter
from paper_digest.paper_sources.arxiv import ArxivSource
from paper_digest.paper_sources.semantic_scholar import SemanticScholarSource
from paper_digest.recommendation.scoring import (
    calculate_popularity,
    calculate_quality,
    calculate_recency,
    calculate_recommendation_score,
    calculate_relevance,
)
from paper_digest.research.profile import ResearchProfileLoader
from paper_digest.services.workflow import PaperWorkflowService

LOGGER = logging.getLogger(__name__)


class DailyRecommendationService:
    """Generate a daily digest of recommended papers."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        arxiv_source: ArxivSource,
        semantic_source: SemanticScholarSource,
        workflow: PaperWorkflowService,
        writer: ObsidianWriter,
        note_index_service: NoteIndexService,
        profile_loader: ResearchProfileLoader,
    ):
        self._settings = settings
        self._arxiv_source = arxiv_source
        self._semantic_source = semantic_source
        self._workflow = workflow
        self._writer = writer
        self._note_index_service = note_index_service
        self._profile_loader = profile_loader

    def recommend(
        self,
        *,
        profile_path: Path,
        top_n: int,
        analyze_top_n: int,
        vault_override: Path | None = None,
        dry_run: bool = False,
        force: bool = False,
        overwrite_strategy: str | None = None,
    ) -> tuple[DailyDigest, list[WriteResult]]:
        profile = self._profile_loader.load(profile_path)
        now = datetime.now(UTC)
        recent_window_start = now - timedelta(days=30)
        hot_window_start = now - timedelta(days=365)
        hot_window_end = now - timedelta(days=31)

        vault_root = self._settings.vault_path(override=vault_override)
        note_index = (
            self._note_index_service.build(vault_root=vault_root, include_root=vault_root)
            if vault_root is not None and vault_root.exists()
            else NoteIndex()
        )

        categories = _combined_categories(profile)
        try:
            recent_candidates = self._arxiv_source.search_recent_by_categories(
                categories=categories,
                start_date=recent_window_start,
                end_date=now,
                max_results=200,
            )
        except Exception as error:
            LOGGER.warning("Skipping recent arXiv recommendations: %s", error)
            recent_candidates = []

        try:
            hot_candidates = self._semantic_source.search_hot_papers(
                categories=categories,
                start_date=hot_window_start,
                end_date=hot_window_end,
                top_k_per_category=5,
            )
        except Exception as error:
            LOGGER.warning("Skipping Semantic Scholar hot recommendations: %s", error)
            hot_candidates = []

        recommended = self._score_candidates(
            recent_candidates=recent_candidates,
            hot_candidates=hot_candidates,
            profile=profile,
            note_index=note_index,
            now=now,
        )
        top_papers = recommended[:top_n]

        analyzed_results = []
        analyzed_summaries = []
        for recommendation in top_papers[:analyze_top_n]:
            if recommendation.already_in_vault or not recommendation.metadata.pdf_url:
                continue
            summary, note_result = self._workflow.summarize_metadata(
                metadata=recommendation.metadata,
                topic=recommendation.matched_domain or self._settings.default_topic,
                dry_run=dry_run,
                force=force,
                overwrite_strategy=overwrite_strategy,
                vault_override=vault_override,
                note_index=note_index,
                extract_images=True,
            )
            recommendation.generated_note_path = note_result.relative_path
            analyzed_results.append(note_result)
            analyzed_summaries.append(summary)

        digest = DailyDigest(
            date=now.date().isoformat(),
            profile_name=profile_path.stem,
            selection_rationale=(
                "同时结合最近 30 天 arXiv 新论文与过去一年中更高影响力的论文，"
                "按研究兴趣相关性、时效性、影响力和摘要质量综合排序。"
            ),
            overview=(
                f"本次根据研究配置从 {len(recent_candidates)} 篇近期 arXiv 论文与 "
                f"{len(hot_candidates)} 篇高影响力候选中筛出 {len(top_papers)} 篇推荐。"
            ),
            recommended_papers=top_papers,
            analyzed_papers=analyzed_summaries,
        )
        daily_result = self._writer.write_daily_digest(
            digest=digest,
            vault_override=vault_override,
            dry_run=dry_run,
            overwrite_strategy=overwrite_strategy,
            note_index=note_index,
        )
        analyzed_results.insert(0, daily_result)
        return digest, analyzed_results

    def _score_candidates(
        self,
        *,
        recent_candidates: list[PaperMetadata],
        hot_candidates: list[dict],
        profile,
        note_index: NoteIndex,
        now: datetime,
    ) -> list[RecommendedPaper]:
        results: list[RecommendedPaper] = []
        seen_ids: set[str] = set()

        recent_items = [(item, 0, 0, "recent") for item in recent_candidates]
        hot_items = [
            (
                self._semantic_source.to_metadata(item),
                int(item.get("citationCount") or 0),
                int(item.get("influentialCitationCount") or 0),
                "hot",
            )
            for item in hot_candidates
        ]
        for metadata, citation_count, influential_citation_count, source_kind in (
            recent_items + hot_items
        ):
            identifier = metadata.arxiv_id or metadata.source_id or metadata.title
            if identifier in seen_ids:
                continue
            seen_ids.add(identifier)

            relevance, matched_domain, matched_keywords = calculate_relevance(
                metadata=metadata,
                profile=profile,
            )
            if relevance <= 0:
                continue

            recency = calculate_recency(metadata.published_at, now=now)
            quality = calculate_quality(metadata.abstract)
            popularity = calculate_popularity(
                influential_citation_count=influential_citation_count,
                citation_count=citation_count,
                is_hot_paper=source_kind == "hot",
            )
            scores = calculate_recommendation_score(
                relevance=relevance,
                recency=recency,
                popularity=popularity,
                quality=quality,
                is_hot_paper=source_kind == "hot",
            )
            existing_paths = _existing_note_paths(note_index, metadata)
            if existing_paths:
                scores.recommendation = round(max(scores.recommendation - 1.5, 0.0), 2)
            results.append(
                RecommendedPaper(
                    metadata=metadata,
                    scores=scores,
                    matched_domain=matched_domain,
                    matched_keywords=matched_keywords,
                    source_kind=source_kind,
                    citation_count=citation_count,
                    influential_citation_count=influential_citation_count,
                    existing_note_paths=existing_paths,
                    already_in_vault=bool(existing_paths),
                )
            )

        return sorted(
            results,
            key=lambda item: (
                item.already_in_vault,
                -item.scores.recommendation,
                item.metadata.title.lower(),
            ),
        )


def _combined_categories(profile) -> list[str]:
    categories: list[str] = []
    for domain in profile.research_domains:
        categories.extend(domain.arxiv_categories)
    return sorted(set(categories or ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.RO"]))


def _existing_note_paths(note_index: NoteIndex, metadata: PaperMetadata) -> list[str]:
    paths: list[str] = []
    metadata_title = metadata.title.lower().strip()
    metadata_arxiv_id = (metadata.arxiv_id or "").lower()
    for note in note_index.notes:
        if metadata_arxiv_id and note.arxiv_id and metadata_arxiv_id == note.arxiv_id.lower():
            paths.append(note.path)
        elif metadata_title and note.title.lower().strip() == metadata_title:
            paths.append(note.path)
    return sorted(set(paths))
