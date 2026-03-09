"""Rebuild topic indexes from existing note files."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from paper_digest.models import PaperMetadata, PaperSummary, WriteResult
from paper_digest.obsidian_writer.writer import ObsidianWriter
from paper_digest.summarizer.heuristic import HeuristicSummarizer
from paper_digest.utils import normalize_whitespace

SECTION_RE = re.compile(r"^##\s+(?P<title>.+)$", flags=re.MULTILINE)

SECTION_ALIASES = {
    "一句话总结": ["一句话总结", "快速结论"],
    "研究背景与问题": ["研究背景与问题"],
    "研究问题": ["研究问题", "我的问题定义"],
    "核心方法": ["核心方法", "核心方法解读"],
    "方法拆解": ["方法拆解"],
    "实验设置": ["实验设置"],
    "主要结果": ["主要结果"],
    "关键结论": ["关键结论"],
    "贡献点": ["贡献点"],
    "局限性": ["局限性"],
    "适用场景": ["适用场景"],
    "建议阅读顺序": ["建议阅读顺序", "建议阅读路线"],
    "我的后续阅读建议": ["我的后续阅读建议"],
    "引用信息": ["引用信息"],
    "原文依据": ["原文依据"],
}


class ObsidianReindexer:
    """Regenerate topic indexes by reading existing markdown notes."""

    def __init__(self, writer: ObsidianWriter):
        self._writer = writer
        self._summarizer = HeuristicSummarizer()

    def rebuild_topic(
        self,
        *,
        topic_dir: Path,
        topic_name: str | None = None,
        dry_run: bool = False,
        overwrite_strategy: str | None = None,
        vault_override: Path | None = None,
    ) -> WriteResult:
        paper_dir = topic_dir / self._writer._settings.papers_dir_name  # noqa: SLF001
        note_paths = sorted(paper_dir.glob("*.md"))
        paper_summaries = [self._load_summary(note_path) for note_path in note_paths]
        topic = topic_name or topic_dir.name.replace("-", " ")
        topic_summary = self._summarizer.summarize_topic(
            topic=topic,
            query=f"reindex:{topic_dir.name}",
            papers=paper_summaries,
        )
        note_results = [
            WriteResult(
                path=note_path,
                relative_path=note_path.as_posix(),
                content=note_path.read_text(encoding="utf-8"),
                written=False,
            )
            for note_path in note_paths
        ]
        return self._writer.write_topic_index(
            topic_summary=topic_summary,
            note_results=note_results,
            topic=topic,
            dry_run=dry_run,
            overwrite_strategy=overwrite_strategy,
            vault_override=vault_override,
        )

    def _load_summary(self, note_path: Path) -> PaperSummary:
        raw = note_path.read_text(encoding="utf-8")
        frontmatter, body = self._split_frontmatter(raw)
        sections = self._parse_sections(body)
        metadata = PaperMetadata(
            source="arxiv",
            source_id=str(frontmatter.get("arxiv_id") or note_path.stem),
            arxiv_id=frontmatter.get("arxiv_id"),
            title=str(frontmatter.get("title") or note_path.stem),
            authors=[str(item) for item in frontmatter.get("authors", [])],
            abstract="",
            year=frontmatter.get("year"),
            pdf_url=str(frontmatter.get("url") or ""),
            abs_url=str(frontmatter.get("url") or ""),
            categories=[],
        )
        return PaperSummary(
            metadata=metadata,
            summary_basis=frontmatter.get("summary_basis") or "基于已有笔记重建",
            one_sentence=self._section(sections, "一句话总结"),
            research_context=self._section(sections, "研究背景与问题"),
            research_problem=self._section(sections, "研究问题"),
            problem_evidence=self._nth_section(sections, "原文依据", 0),
            core_method=self._section(sections, "核心方法"),
            method_evidence=self._nth_section(sections, "原文依据", 1),
            method_breakdown=_to_list(self._section(sections, "方法拆解")),
            experiment_setup=_to_list(self._section(sections, "实验设置")),
            main_results=self._section(sections, "主要结果"),
            results_evidence=self._nth_section(sections, "原文依据", 2),
            key_findings=_to_list(self._section(sections, "关键结论")),
            contributions=_to_list(self._section(sections, "贡献点")),
            limitations=_to_list(self._section(sections, "局限性")),
            use_cases=_to_list(self._section(sections, "适用场景")),
            follow_up_advice=_to_list(self._section(sections, "我的后续阅读建议")),
            reading_path=_to_list(self._section(sections, "建议阅读顺序")),
            citation=self._section(sections, "引用信息"),
            short_overview=[
                self._section(sections, "一句话总结"),
                self._section(sections, "研究问题"),
                self._section(sections, "核心方法"),
                self._section(sections, "主要结果"),
            ],
            problem_definition=normalize_whitespace(self._section(sections, "研究问题")),
            method_category="重建索引",
            datasets_or_benchmarks="",
            strengths=_to_list(self._section(sections, "关键结论")),
            weaknesses=_to_list(self._section(sections, "局限性")),
            paper_role="core method",
        )

    @staticmethod
    def _split_frontmatter(content: str) -> tuple[dict, str]:
        if not content.startswith("---\n"):
            return {}, content
        _, frontmatter, body = content.split("---", 2)
        return yaml.safe_load(frontmatter) or {}, body.strip()

    @staticmethod
    def _parse_sections(body: str) -> dict[str, list[str]]:
        matches = list(SECTION_RE.finditer(body))
        sections: dict[str, list[str]] = {}
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            title = match.group("title").strip()
            section_body = normalize_whitespace(body[start:end].strip())
            sections.setdefault(title, []).append(section_body)
        return sections

    @staticmethod
    def _section(sections: dict[str, list[str]], canonical: str) -> str:
        for alias in SECTION_ALIASES.get(canonical, [canonical]):
            values = sections.get(alias)
            if values:
                return values[0]
        return ""

    @staticmethod
    def _nth_section(sections: dict[str, list[str]], canonical: str, index: int) -> str:
        values: list[str] = []
        for alias in SECTION_ALIASES.get(canonical, [canonical]):
            values.extend(sections.get(alias, []))
        return values[index] if len(values) > index else ""


def _to_list(value: str) -> list[str]:
    items = []
    for line in value.splitlines():
        cleaned = line.strip().lstrip("-").strip()
        if cleaned:
            items.append(cleaned)
    return items
