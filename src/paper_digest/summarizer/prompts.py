"""Prompt builders for optional LLM-backed summarization."""

from __future__ import annotations

from textwrap import dedent
from typing import Literal

from paper_digest.models import PaperSummary, ParsedPaper, TopicSummary
from paper_digest.utils import truncate_text

Audience = Literal["technical", "beginner"]
DetailLevel = Literal["standard", "detailed"]


def build_paper_summary_prompt(
    parsed_paper: ParsedPaper,
    *,
    baseline_summary: PaperSummary | None = None,
    audience: Audience = "beginner",
    detail_level: DetailLevel = "detailed",
) -> str:
    """Render a prompt for one paper summary."""

    metadata = parsed_paper.metadata
    section_snapshot = []
    for section in parsed_paper.sections[:8]:
        section_snapshot.append(
            f"[{section.heading}]\n{truncate_text(section.body, max_chars=1500)}"
        )
    section_text = "\n\n".join(section_snapshot) or "(No sections extracted)"

    baseline_block = ""
    if baseline_summary is not None:
        baseline_block = dedent(f"""
            规则摘要草稿（只能作为辅助参考，如与原文冲突，以原文为准）：
            - 一句话总结：{baseline_summary.one_sentence}
            - 研究问题：{baseline_summary.research_problem}
            - 核心方法：{baseline_summary.core_method}
            - 数据集 / 基准：{baseline_summary.datasets_or_benchmarks}
            - 结果：{baseline_summary.main_results}
            """).strip()

    return dedent(f"""
        你是一名耐心、诚实、擅长把论文讲给初学者听懂的中文论文导师。
        你的任务不是炫技，而是把论文真正讲清楚。
        只返回一个 JSON 对象，不要输出 Markdown、解释文字、代码块或前后缀。

        目标读者：
        {_audience_instruction(audience=audience, detail_level=detail_level)}

        你必须优先回答清楚这四件事：
        1. 这篇论文用了什么模型、框架或关键模块？
        2. 它具体做了什么，想解决什么问题？
        3. 它用了什么数据集或基准？
        4. 它的实验结果如何，提升体现在什么地方？

        JSON schema:
        {{
          "summary_basis": "string",
          "one_sentence": "string",
          "research_context": "string",
          "research_problem": "string",
          "problem_evidence": "string",
          "core_method": "string",
          "method_evidence": "string",
          "method_breakdown": ["string"],
          "experiment_setup": ["string"],
          "main_results": "string",
          "results_evidence": "string",
          "key_findings": ["string"],
          "figure_reading_tips": ["string"],
          "contributions": ["string"],
          "limitations": ["string"],
          "use_cases": ["string"],
          "follow_up_advice": ["string"],
          "reading_path": ["string"],
          "citation": "string",
          "short_overview": ["string"],
          "problem_definition": "string",
          "method_category": "string",
          "datasets_or_benchmarks": "string",
          "strengths": ["string"],
          "weaknesses": ["string"],
          "paper_role": "string"
        }}

        硬约束：
        - 只根据提供的标题、摘要、正文摘录和规则摘要草稿来写，不要编造事实。
        - 如果全文提取不足，`summary_basis` 必须明确写“基于摘要和可提取正文生成”、
          “基于摘要和部分可提取正文生成”或“仅基于摘要生成”。
        - 全部用中文输出。
        - 面向初学者时，先讲人话，再讲术语；如果必须使用术语，请紧跟一句白话解释。
        - `one_sentence` 用 1 到 2 句。
        - `research_context`、`research_problem`、`core_method`、`main_results` 各写 2 到 4 句。
        - 列表字段的每一项都写成完整短句，不要只写名词。
        - `short_overview` 输出 4 到 5 条，适合放在笔记最顶部给完全没基础的人快速理解。
        - `paper_role` 只能是 `survey`、`benchmark`、`framework`、`dataset`、`core method` 之一。
        - 如果数据集、指标或结果数字没有被明确提到，要直接说明“正文摘录中未明确给出”，不要猜。

        Title: {metadata.title}
        Authors: {", ".join(metadata.authors)}
        arXiv: {metadata.arxiv_id or metadata.source_id}

        Abstract:
        {truncate_text(parsed_paper.combined_abstract, max_chars=4000)}

        Section excerpts:
        {section_text}

        {baseline_block}
        """).strip()


def build_topic_summary_prompt(
    *,
    topic: str,
    query: str,
    papers: list[PaperSummary],
    baseline_summary: TopicSummary | None = None,
    audience: Audience = "beginner",
    detail_level: DetailLevel = "detailed",
) -> str:
    """Render a prompt for multi-paper summary."""

    paper_blocks = []
    for paper in papers:
        paper_blocks.append(dedent(f"""
                Title: {paper.metadata.title}
                Role: {paper.paper_role}
                One sentence: {paper.one_sentence}
                Problem: {paper.problem_definition}
                Method category: {paper.method_category}
                Core method: {paper.core_method}
                Datasets / benchmarks: {paper.datasets_or_benchmarks}
                Results: {paper.main_results}
                Strengths: {"; ".join(paper.strengths)}
                Limitations: {"; ".join(paper.weaknesses or paper.limitations)}
                """).strip())

    baseline_block = ""
    if baseline_summary is not None:
        baseline_block = dedent(f"""
            规则化专题摘要草稿（仅作辅助参考）：
            - 概览：{baseline_summary.overview}
            - 选文理由：{baseline_summary.selection_rationale}
            - 为什么是这些论文：{baseline_summary.why_these_papers}
            """).strip()

    paper_text = "\n\n".join(paper_blocks)
    return dedent(f"""
        你是一名耐心的中文研究导师，请把下面的论文集合整理成一个适合初学者的专题索引。
        只返回一个 JSON 对象，不要输出 Markdown、解释文字或代码块。

        目标读者：
        {_audience_instruction(audience=audience, detail_level=detail_level)}

        JSON fields:
        {{
          "selection_rationale": "string",
          "why_these_papers": "string",
          "overview": "string",
          "reading_order": ["string"]
        }}

        约束：
        - `overview` 要先讲这个方向近几年的主线，再讲这批论文分别扮演什么角色。
        - `selection_rationale` 要解释为什么选它们，而不是泛泛地说“代表性强”。
        - `why_these_papers` 要强调每篇在演化链条中的位置。
        - `reading_order` 要给出适合初学者的阅读顺序，每条都带理由。
        - 不要编造未提供的论文信息。

        Topic: {topic}
        Query: {query}

        Papers:
        {paper_text}

        {baseline_block}
        """).strip()


def _audience_instruction(*, audience: Audience, detail_level: DetailLevel) -> str:
    if audience == "technical":
        detail = "读者有一定论文阅读基础，可以保留必要术语，但仍要先给出结论。"
    else:
        detail = (
            "读者基础较弱，默认把内容讲给刚接触这个方向的人听。"
            "先解释问题，再解释模型；先讲直觉，再讲模块。"
        )

    granularity = (
        "内容尽量详细，关键模块、数据集、指标和实验结论都要点明。"
        if detail_level == "detailed"
        else "内容可以简洁，但核心问题、方法、数据集和结果必须完整。"
    )
    return f"{detail} {granularity}"
