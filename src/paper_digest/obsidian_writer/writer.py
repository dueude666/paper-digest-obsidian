"""Obsidian note writing utilities."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paper_digest.config import AppSettings
from paper_digest.exceptions import ConfigurationError
from paper_digest.knowledge.linker import MarkdownAutoLinker
from paper_digest.models import (
    DailyDigest,
    ImageAsset,
    NoteIndex,
    PaperFullView,
    PaperMetadata,
    PaperSummary,
    ParsedPaper,
    TopicSummary,
    WriteResult,
)
from paper_digest.obsidian_writer.renderers import MarkdownRenderer
from paper_digest.utils import dedupe_preserve_order, ensure_directory, slugify


class ObsidianWriter:
    """Render and persist markdown notes under an Obsidian vault."""

    def __init__(
        self,
        settings: AppSettings,
        renderer: MarkdownRenderer | None = None,
        linker: MarkdownAutoLinker | None = None,
    ):
        self._settings = settings
        self._renderer = renderer or MarkdownRenderer()
        self._linker = linker or MarkdownAutoLinker()

    def write_paper(
        self,
        *,
        summary: PaperSummary,
        topic: str,
        vault_override: Path | None = None,
        dry_run: bool = False,
        overwrite_strategy: str | None = None,
        note_index: NoteIndex | None = None,
        image_assets: list[ImageAsset] | None = None,
    ) -> WriteResult:
        topic_slug = self.topic_slug(topic)
        paper_slug = self.paper_slug(summary)
        topic_root = self._topic_root(
            topic_slug=topic_slug, vault_override=vault_override, dry_run=dry_run
        )
        note_path = topic_root / self._settings.papers_dir_name / f"{paper_slug}.md"
        image_context = [
            {
                "embed": f"../{self._settings.assets_dir_name}/{paper_slug}/{asset.filename}",
                "filename": asset.filename,
                "source": asset.source,
            }
            for asset in (image_assets or [])[:8]
        ]
        content = self._renderer.render_paper(
            summary=summary,
            topic_name=topic,
            frontmatter=self._paper_frontmatter(summary=summary, topic_slug=topic_slug),
            topic_index_target=f"{self._settings.literature_dir_name}/{topic_slug}/index",
            image_assets=image_context,
            role_display=_paper_role_display(summary.paper_role),
        )
        resolved_path, skipped = self._resolve_output_path(
            note_path,
            overwrite_strategy or self._settings.overwrite_strategy,
        )
        relative_path = self._relative_path(
            resolved_path, vault_override=vault_override, dry_run=dry_run
        )
        content = self._auto_link(
            content=content,
            note_index=note_index,
            exclude_paths={relative_path},
        )

        if not dry_run and not skipped:
            ensure_directory(resolved_path.parent)
            ensure_directory(topic_root / self._settings.assets_dir_name / paper_slug)
            resolved_path.write_text(content, encoding="utf-8")

        return WriteResult(
            path=resolved_path,
            relative_path=relative_path,
            content=content,
            written=not dry_run and not skipped,
            skipped=skipped,
        )

    def write_topic_index(
        self,
        *,
        topic_summary: TopicSummary,
        note_results: list[WriteResult],
        topic: str,
        vault_override: Path | None = None,
        dry_run: bool = False,
        overwrite_strategy: str | None = None,
        note_index: NoteIndex | None = None,
    ) -> WriteResult:
        topic_slug = self.topic_slug(topic)
        topic_root = self._topic_root(
            topic_slug=topic_slug, vault_override=vault_override, dry_run=dry_run
        )
        note_lookup = {note.path.stem: note for note in note_results}
        notes_context: list[dict[str, Any]] = []
        comparison_rows: list[dict[str, Any]] = []

        for paper in topic_summary.papers:
            paper_slug = self.paper_slug(paper)
            note = note_lookup.get(paper_slug)
            link = f"[[{self._settings.papers_dir_name}/{paper_slug}|{paper.metadata.title}]]"
            notes_context.append(
                {
                    "title": paper.metadata.title,
                    "wikilink": link,
                    "paper_role": _paper_role_display(paper.paper_role),
                    "method_category": paper.method_category,
                    "datasets_or_benchmarks": paper.datasets_or_benchmarks,
                    "short_overview": paper.short_overview,
                    "relative_path": (
                        note.relative_path
                        if note
                        else f"{topic_slug}/{self._settings.papers_dir_name}/{paper_slug}.md"
                    ),
                }
            )
            comparison_rows.append(
                {
                    "wikilink": link,
                    "problem_definition": paper.problem_definition,
                    "method_category": paper.method_category,
                    "datasets_or_benchmarks": paper.datasets_or_benchmarks,
                    "strengths": "；".join(paper.strengths),
                    "limitations": "；".join(paper.weaknesses or paper.limitations),
                }
            )

        index_path = topic_root / "index.md"
        content = self._renderer.render_topic_index(
            topic_summary=topic_summary,
            frontmatter=self._topic_frontmatter(topic_summary=topic_summary, topic_slug=topic_slug),
            notes=notes_context,
            comparison_rows=comparison_rows,
        )
        resolved_path, skipped = self._resolve_output_path(
            index_path,
            overwrite_strategy or self._settings.overwrite_strategy,
        )
        relative_path = self._relative_path(
            resolved_path, vault_override=vault_override, dry_run=dry_run
        )
        content = self._auto_link(
            content=content,
            note_index=note_index,
            exclude_paths={relative_path},
        )

        if not dry_run and not skipped:
            ensure_directory(resolved_path.parent)
            resolved_path.write_text(content, encoding="utf-8")

        return WriteResult(
            path=resolved_path,
            relative_path=relative_path,
            content=content,
            written=not dry_run and not skipped,
            skipped=skipped,
        )

    def write_full_paper(
        self,
        *,
        parsed_paper: ParsedPaper,
        topic: str,
        pdf_source_path: Path | None = None,
        vault_override: Path | None = None,
        dry_run: bool = False,
        overwrite_strategy: str | None = None,
    ) -> WriteResult:
        strategy = overwrite_strategy or self._settings.overwrite_strategy
        full_view = self.build_full_view(
            parsed_paper=parsed_paper,
            topic=topic,
            pdf_source_path=pdf_source_path,
            vault_override=vault_override,
            dry_run=dry_run,
        )
        topic_slug = full_view.topic_slug
        paper_slug = full_view.paper_slug
        topic_root = self._topic_root(
            topic_slug=topic_slug, vault_override=vault_override, dry_run=dry_run
        )
        note_path = topic_root / self._settings.full_text_dir_name / f"{paper_slug}.md"
        pdf_asset_path = (
            topic_root / self._settings.assets_dir_name / paper_slug / f"{paper_slug}.pdf"
            if pdf_source_path is not None
            else None
        )
        content = self._renderer.render_full_paper(
            full_view=full_view,
            frontmatter=self._full_paper_frontmatter(full_view=full_view),
        )
        resolved_path, skipped = self._resolve_output_path(
            note_path,
            strategy,
        )
        relative_path = self._relative_path(
            resolved_path, vault_override=vault_override, dry_run=dry_run
        )

        if not dry_run and not skipped:
            ensure_directory(resolved_path.parent)
            if pdf_source_path is not None and pdf_asset_path is not None:
                ensure_directory(pdf_asset_path.parent)
                if not pdf_asset_path.exists() or strategy == "overwrite":
                    shutil.copy2(pdf_source_path, pdf_asset_path)
            resolved_path.write_text(content, encoding="utf-8")

        return WriteResult(
            path=resolved_path,
            relative_path=relative_path,
            content=content,
            written=not dry_run and not skipped,
            skipped=skipped,
        )

    def write_source_pdf(
        self,
        *,
        metadata: PaperMetadata,
        topic: str,
        pdf_source_path: Path,
        vault_override: Path | None = None,
        dry_run: bool = False,
        overwrite_strategy: str | None = None,
    ) -> WriteResult:
        topic_slug = self.topic_slug(topic)
        paper_slug = self.paper_slug_from_metadata(metadata)
        topic_root = self._topic_root(
            topic_slug=topic_slug, vault_override=vault_override, dry_run=dry_run
        )
        output_path = topic_root / self._settings.pdf_dir_name / f"{paper_slug}.pdf"
        resolved_path, skipped = self._resolve_output_path(
            output_path,
            overwrite_strategy or self._settings.overwrite_strategy,
        )
        relative_path = self._relative_path(
            resolved_path, vault_override=vault_override, dry_run=dry_run
        )

        if not dry_run and not skipped:
            ensure_directory(resolved_path.parent)
            shutil.copy2(pdf_source_path, resolved_path)

        return WriteResult(
            path=resolved_path,
            relative_path=relative_path,
            content="",
            written=not dry_run and not skipped,
            skipped=skipped,
        )

    def build_full_view(
        self,
        *,
        parsed_paper: ParsedPaper,
        topic: str,
        pdf_source_path: Path | None = None,
        vault_override: Path | None = None,
        dry_run: bool = False,
    ) -> PaperFullView:
        topic_slug = self.topic_slug(topic)
        paper_slug = self.paper_slug_from_metadata(parsed_paper.metadata)
        topic_root = self._topic_root(
            topic_slug=topic_slug, vault_override=vault_override, dry_run=dry_run
        )
        pdf_asset_relative_path: str | None = None
        pdf_embed_target: str | None = None
        if pdf_source_path is not None:
            pdf_asset_path = (
                topic_root / self._settings.assets_dir_name / paper_slug / f"{paper_slug}.pdf"
            )
            pdf_asset_relative_path = self._relative_path(
                pdf_asset_path,
                vault_override=vault_override,
                dry_run=dry_run,
            )
            pdf_embed_target = f"../{self._settings.assets_dir_name}/{paper_slug}/{paper_slug}.pdf"

        return PaperFullView(
            metadata=parsed_paper.metadata,
            parsed_paper=parsed_paper,
            topic_name=topic,
            topic_slug=topic_slug,
            paper_slug=paper_slug,
            topic_index_target=f"{self._settings.literature_dir_name}/{topic_slug}/index",
            summary_note_target=(
                f"{self._settings.literature_dir_name}/{topic_slug}/"
                f"{self._settings.papers_dir_name}/{paper_slug}"
            ),
            pdf_asset_relative_path=pdf_asset_relative_path,
            pdf_embed_target=pdf_embed_target,
        )

    def write_daily_digest(
        self,
        *,
        digest: DailyDigest,
        vault_override: Path | None = None,
        dry_run: bool = False,
        overwrite_strategy: str | None = None,
        note_index: NoteIndex | None = None,
    ) -> WriteResult:
        daily_root = self._daily_root(vault_override=vault_override, dry_run=dry_run)
        note_path = daily_root / f"{digest.date}-论文推荐.md"
        recommended_papers = []
        for paper in digest.recommended_papers:
            primary_target = paper.generated_note_path or (
                paper.existing_note_paths[0] if paper.existing_note_paths else None
            )
            link = (
                f"[[{_note_target(primary_target)}|{paper.metadata.title}]]"
                if primary_target
                else paper.metadata.title
            )
            existing_links = [f"[[{_note_target(path)}]]" for path in paper.existing_note_paths]
            recommended_papers.append(
                {
                    "link": link,
                    "domain": paper.matched_domain or "未分类",
                    "source_kind": "近期论文" if paper.source_kind == "recent" else "高影响论文",
                    "score": paper.scores.recommendation,
                    "matched_keywords": "、".join(paper.matched_keywords) or "未提取",
                    "status": "已在库中" if paper.already_in_vault else "新生成",
                    "existing_note_links": existing_links,
                    "overview": [
                        paper.metadata.title,
                        paper.metadata.abstract[:240].replace("\n", " "),
                    ],
                }
            )

        content = self._renderer.render_daily_digest(
            digest=digest,
            frontmatter=self._daily_frontmatter(digest=digest),
            recommended_papers=recommended_papers,
        )
        resolved_path, skipped = self._resolve_output_path(
            note_path,
            overwrite_strategy or self._settings.overwrite_strategy,
        )
        relative_path = self._relative_path(
            resolved_path, vault_override=vault_override, dry_run=dry_run
        )
        content = self._auto_link(
            content=content,
            note_index=note_index,
            exclude_paths={relative_path},
        )

        if not dry_run and not skipped:
            ensure_directory(resolved_path.parent)
            resolved_path.write_text(content, encoding="utf-8")

        return WriteResult(
            path=resolved_path,
            relative_path=relative_path,
            content=content,
            written=not dry_run and not skipped,
            skipped=skipped,
        )

    def paper_slug(self, summary: PaperSummary) -> str:
        return self.paper_slug_from_metadata(summary.metadata)

    def paper_slug_from_metadata(self, metadata: PaperMetadata) -> str:
        identifier = metadata.arxiv_id or metadata.source_id
        identifier_slug = slugify(identifier, max_length=32)
        title_slug = slugify(metadata.title, max_length=60)
        year = metadata.year or "paper"
        return f"{year}-{identifier_slug}-{title_slug}".strip("-")

    def topic_slug(self, topic: str) -> str:
        return slugify(topic or self._settings.default_topic, max_length=60)

    def topic_root(
        self,
        *,
        topic_slug: str,
        vault_override: Path | None = None,
        dry_run: bool = False,
    ) -> Path:
        return self._topic_root(
            topic_slug=topic_slug,
            vault_override=vault_override,
            dry_run=dry_run,
        )

    def daily_root(self, *, vault_override: Path | None = None, dry_run: bool = False) -> Path:
        return self._daily_root(vault_override=vault_override, dry_run=dry_run)

    def relative_path(
        self,
        path: Path,
        *,
        vault_override: Path | None = None,
        dry_run: bool = False,
    ) -> str:
        return self._relative_path(path, vault_override=vault_override, dry_run=dry_run)

    def _paper_frontmatter(self, *, summary: PaperSummary, topic_slug: str) -> dict[str, Any]:
        tags = [
            "文献",
            "论文笔记",
            f"主题/{topic_slug}",
            summary.metadata.source,
        ]
        tags.extend(
            f"arxiv/{category.lower().replace('.', '-')}"
            for category in summary.metadata.categories[:3]
        )
        return {
            "title": summary.metadata.title,
            "authors": summary.metadata.authors,
            "year": summary.metadata.year,
            "arxiv_id": summary.metadata.arxiv_id,
            "url": summary.metadata.abs_url,
            "tags": dedupe_preserve_order(tags),
            "created": datetime.now(UTC).isoformat(),
        }

    def _topic_frontmatter(self, *, topic_summary: TopicSummary, topic_slug: str) -> dict[str, Any]:
        return {
            "title": f"{topic_summary.topic} - 专题索引",
            "topic": topic_summary.topic,
            "query": topic_summary.query,
            "paper_count": len(topic_summary.papers),
            "tags": ["文献", "专题索引", f"主题/{topic_slug}"],
            "created": datetime.now(UTC).isoformat(),
        }

    def _full_paper_frontmatter(self, *, full_view: PaperFullView) -> dict[str, Any]:
        metadata = full_view.metadata
        tags = [
            "文献",
            "论文全文",
            f"主题/{full_view.topic_slug}",
            metadata.source,
        ]
        return {
            "title": f"{metadata.title} 全文查看",
            "paper_title": metadata.title,
            "authors": metadata.authors,
            "year": metadata.year,
            "arxiv_id": metadata.arxiv_id,
            "url": metadata.abs_url,
            "pdf_path": full_view.pdf_asset_relative_path,
            "tags": dedupe_preserve_order(tags),
            "created": datetime.now(UTC).isoformat(),
        }

    def _topic_root(self, *, topic_slug: str, vault_override: Path | None, dry_run: bool) -> Path:
        vault = self._settings.vault_path(override=vault_override)
        if vault is None and not dry_run:
            raise ConfigurationError("Obsidian vault path is not configured. Use --vault or .env.")
        base = vault if vault is not None else Path.cwd() / "_dry_run_vault"
        return base / self._settings.literature_dir_name / topic_slug

    def _daily_root(self, *, vault_override: Path | None, dry_run: bool) -> Path:
        vault = self._settings.vault_path(override=vault_override)
        if vault is None and not dry_run:
            raise ConfigurationError("Obsidian vault path is not configured. Use --vault or .env.")
        base = vault if vault is not None else Path.cwd() / "_dry_run_vault"
        return base / self._settings.literature_dir_name / self._settings.daily_dir_name

    @staticmethod
    def _resolve_output_path(path: Path, strategy: str) -> tuple[Path, bool]:
        if not path.exists():
            return path, False
        if strategy == "overwrite":
            return path, False
        if strategy == "skip":
            return path, True
        if strategy == "suffix":
            index = 2
            while True:
                candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
                if not candidate.exists():
                    return candidate, False
                index += 1
        raise ValueError(f"Unknown overwrite strategy: {strategy}")

    def _relative_path(self, path: Path, *, vault_override: Path | None, dry_run: bool) -> str:
        vault = self._settings.vault_path(override=vault_override)
        if vault is None and dry_run:
            return path.as_posix()
        if vault is None:
            return path.name
        return path.relative_to(vault).as_posix()

    def _daily_frontmatter(self, *, digest: DailyDigest) -> dict[str, Any]:
        return {
            "title": f"{digest.date} 论文推荐",
            "date": digest.date,
            "profile": digest.profile_name,
            "paper_count": len(digest.recommended_papers),
            "tags": ["文献", "每日推荐", "推荐清单"],
            "created": datetime.now(UTC).isoformat(),
        }

    def _auto_link(
        self,
        *,
        content: str,
        note_index: NoteIndex | None,
        exclude_paths: set[str],
    ) -> str:
        if note_index is None or not self._settings.auto_link_existing_notes:
            return content
        return self._linker.link(
            content=content, note_index=note_index, exclude_paths=exclude_paths
        )


def _note_target(path: str | None) -> str:
    if path is None:
        return ""
    return path[:-3] if path.endswith(".md") else path


def _paper_role_display(role: str) -> str:
    mapping = {
        "survey": "综述",
        "benchmark": "评测 / 基准",
        "framework": "框架",
        "dataset": "数据集",
        "core method": "核心方法",
    }
    return mapping.get(role, role or "未标注")
