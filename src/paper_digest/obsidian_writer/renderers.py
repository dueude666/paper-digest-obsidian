"""Markdown rendering helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

from paper_digest.models import DailyDigest, PaperFullView, PaperSummary, TopicSummary


class MarkdownRenderer:
    """Render note templates into Obsidian-friendly markdown."""

    def __init__(self):
        template_dir = Path(__file__).resolve().parent.parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_paper(
        self,
        *,
        summary: PaperSummary,
        frontmatter: dict[str, Any],
        topic_name: str,
        topic_index_target: str,
        image_assets: list[dict[str, Any]],
        role_display: str,
    ) -> str:
        template = self._env.get_template("paper_note.md.j2")
        return template.render(
            frontmatter=self._dump_frontmatter(frontmatter),
            summary=summary,
            topic_name=topic_name,
            topic_index_target=topic_index_target,
            image_assets=image_assets,
            role_display=role_display,
        )

    def render_topic_index(
        self,
        *,
        topic_summary: TopicSummary,
        frontmatter: dict[str, Any],
        notes: list[dict[str, Any]],
        comparison_rows: list[dict[str, Any]],
    ) -> str:
        template = self._env.get_template("topic_index.md.j2")
        return template.render(
            frontmatter=self._dump_frontmatter(frontmatter),
            topic_summary=topic_summary,
            notes=notes,
            comparison_rows=comparison_rows,
        )

    def render_full_paper(
        self,
        *,
        full_view: PaperFullView,
        frontmatter: dict[str, Any],
    ) -> str:
        template = self._env.get_template("paper_full_view.md.j2")
        return template.render(
            frontmatter=self._dump_frontmatter(frontmatter),
            full_view=full_view,
        )

    def render_daily_digest(
        self,
        *,
        digest: DailyDigest,
        frontmatter: dict[str, Any],
        recommended_papers: list[dict[str, Any]],
    ) -> str:
        template = self._env.get_template("daily_digest.md.j2")
        return template.render(
            frontmatter=self._dump_frontmatter(frontmatter),
            digest=digest,
            recommended_papers=recommended_papers,
        )

    @staticmethod
    def _dump_frontmatter(frontmatter: dict[str, Any]) -> str:
        yaml_text = yaml.safe_dump(
            frontmatter,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ).strip()
        return f"---\n{yaml_text}\n---"
