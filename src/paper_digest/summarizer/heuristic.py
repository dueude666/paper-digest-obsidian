"""Rule-based summarizer used by the MVP."""

from __future__ import annotations

from collections import Counter

from paper_digest.models import (
    PaperMetadata,
    PaperSummary,
    ParsedPaper,
    TopicComparisonRow,
    TopicSummary,
)
from paper_digest.summarizer.base import SummaryEngine
from paper_digest.utils import dedupe_preserve_order, format_authors, split_sentences, truncate_text

KNOWN_BENCHMARKS = [
    "nuScenes",
    "Waymo",
    "KITTI",
    "Argoverse",
    "Argoverse 2",
    "BDD100K",
    "nuPlan",
    "DOTA",
    "DIOR",
    "DIOR-R",
    "HRSC2016",
    "VisDrone",
    "AI-TOD",
    "AI-TOD-v2",
    "CODrone",
    "FAIR1M",
    "MS MARCO",
    "Natural Questions",
    "HotpotQA",
    "TriviaQA",
    "BEIR",
    "MTEB",
    "SQuAD",
    "LongBench",
    "MMLU",
    "GSM8K",
]

METRIC_KEYWORDS = [
    "NDS",
    "mAP",
    "AP",
    "IoU",
    "Recall",
    "Precision",
    "FPS",
    "latency",
    "throughput",
    "AMOTA",
    "AMOTP",
    "mIoU",
]

FULL_TEXT_BASIS = "基于摘要和可提取正文生成"
PARTIAL_TEXT_BASIS = "基于摘要和部分可提取正文生成"
ABSTRACT_ONLY_BASIS = "仅基于摘要生成"
UNKNOWN_BENCHMARK = "正文摘录中未明确给出统一数据集/基准"
CORE_METHOD_LABEL = "核心方法"


class HeuristicSummarizer(SummaryEngine):
    """Deterministic summarizer that works without any external model."""

    def summarize_paper(self, parsed_paper: ParsedPaper) -> PaperSummary:
        metadata = parsed_paper.metadata
        abstract = parsed_paper.combined_abstract
        section_map = {section.heading.lower(): section.body for section in parsed_paper.sections}

        intro_text = self._pick_section(
            section_map,
            ["introduction", "1 introduction", "background", "motivation"],
        )
        method_text = self._pick_section(
            section_map,
            ["method", "approach", "framework", "model", "proposed method", "system"],
        )
        results_text = self._pick_section(
            section_map,
            ["experiments", "experiment", "evaluation", "results", "analysis"],
        )
        conclusion_text = self._pick_section(
            section_map,
            ["discussion", "limitations", "conclusion", "future work"],
        )

        combined = " ".join([metadata.title, abstract, intro_text, method_text, results_text])
        basis = self._summary_basis(parsed_paper)
        task_focus = self._detect_task(combined)
        method_focus = self._detect_method_focus(combined)
        challenge_focus = self._detect_challenges(combined)
        evidence_text = " ".join([results_text, conclusion_text, abstract])
        benchmarks = self._extract_benchmarks(evidence_text)
        metrics = self._extract_metrics(evidence_text)

        problem_evidence = self._compose_evidence(
            [intro_text, abstract],
            keywords=["problem", "challenge", "task", "goal", "focus", "address"],
            fallback=abstract,
        )
        method_evidence = self._compose_evidence(
            [method_text, abstract],
            keywords=[
                "method",
                "approach",
                "framework",
                "query",
                "transformer",
                "fusion",
                "bev",
                "position",
                "temporal",
                "sparse",
                "rotated",
                "remote sensing",
                "uav",
                "retrieval",
            ],
            fallback=abstract,
        )
        results_evidence = self._compose_evidence(
            [results_text, conclusion_text, abstract],
            keywords=[
                "result",
                "outperform",
                "benchmark",
                "improve",
                "performance",
                "efficient",
                "state-of-the-art",
                "sota",
            ],
            fallback=abstract,
        )

        method_breakdown = self._build_method_breakdown(combined)
        experiment_setup = self._build_experiment_setup(benchmarks=benchmarks, metrics=metrics)
        strengths = self._build_strengths(combined, benchmarks=benchmarks)
        limitations = self._build_limitations(combined, basis=basis)
        key_findings = self._build_key_findings(
            strengths=strengths,
            benchmarks=benchmarks,
            metrics=metrics,
        )
        contributions = self._build_contributions(
            task_focus=task_focus,
            method_focus=method_focus,
            method_breakdown=method_breakdown,
            benchmarks=benchmarks,
        )
        use_cases = self._infer_use_cases(combined)
        follow_up_advice = self._follow_up_advice(parsed_paper, basis)
        reading_path = self._build_reading_path(parsed_paper)
        figure_reading_tips = self._build_figure_reading_tips(combined)

        benchmark_label = benchmarks or "相关基准"
        metric_label = metrics or "关键指标"
        leading_strength = strengths[0] if strengths else "给出了有参考价值的实验结果。"

        one_sentence = (
            f"这篇论文聚焦{task_focus}，通过{method_focus}来缓解{challenge_focus}，"
            f"并在{benchmark_label}上验证了方法有效性。"
        )
        research_context = (
            f"论文针对{task_focus}展开。这个方向长期面对的难点主要是{challenge_focus}。"
            "作者的核心目标不是只把模型做得更复杂，而是把几何建模、信息聚合和工程可用性一起考虑，"
            "让方法在真实任务里更稳定。"
        )
        research_problem = (
            f"作者真正想解决的问题是：在{task_focus}任务里，如何在不丢失关键信息的前提下，"
            f"更稳地处理{challenge_focus}，并把收益落到可以复现的实验提升上。"
        )
        core_method = (
            f"方法上，论文提出了{method_focus}。整体思路通常围绕特征编码、查询构造和预测解码展开，"
            "让模型先把分散的输入整理到统一表示空间里，再输出最终的检测、检索或推理结果。"
        )
        main_results = (
            f"实验部分主要在{benchmark_label}上报告结果，重点关注{metric_label}等指标。"
            f"整体结论是：{leading_strength}"
        )

        return PaperSummary(
            metadata=metadata,
            summary_basis=basis,
            one_sentence=truncate_text(one_sentence, 240),
            research_context=truncate_text(research_context, 500),
            research_problem=truncate_text(research_problem, 500),
            problem_evidence=truncate_text(problem_evidence, 600),
            core_method=truncate_text(core_method, 600),
            method_evidence=truncate_text(method_evidence, 700),
            method_breakdown=method_breakdown[:5],
            experiment_setup=experiment_setup[:4],
            main_results=truncate_text(main_results, 500),
            results_evidence=truncate_text(results_evidence, 700),
            key_findings=key_findings[:4],
            figure_reading_tips=figure_reading_tips[:4],
            contributions=contributions[:4],
            limitations=limitations[:4],
            use_cases=use_cases[:4],
            follow_up_advice=follow_up_advice[:4],
            reading_path=reading_path[:4],
            citation=self._build_citation(metadata),
            short_overview=[
                truncate_text(one_sentence, 180),
                truncate_text(research_problem, 180),
                truncate_text(core_method, 180),
                truncate_text(main_results, 180),
            ],
            problem_definition=truncate_text(f"{task_focus}：{challenge_focus}", 180),
            method_category=self._classify_method(metadata.title, abstract),
            datasets_or_benchmarks=benchmarks,
            strengths=strengths[:3],
            weaknesses=limitations[:3],
            paper_role=self._classify_role(metadata.title, abstract),
            warnings=parsed_paper.warnings,
        )

    def summarize_topic(self, topic: str, query: str, papers: list[PaperSummary]) -> TopicSummary:
        papers = sorted(papers, key=self._topic_sort_key)
        category_counts = Counter(
            paper.method_category for paper in papers if paper.method_category
        )
        role_counts = Counter(paper.paper_role for paper in papers if paper.paper_role)
        dominant_categories = (
            "、".join([name for name, _ in category_counts.most_common(3)]) or "多种方法路线"
        )
        reading_order = [
            (
                f"{index}. {paper.metadata.title}：先看它如何定义问题，再看它属于"
                f"{paper.method_category or CORE_METHOD_LABEL}路线，最后对照主实验表。"
            )
            for index, paper in enumerate(papers, start=1)
        ]
        comparison_rows = [
            TopicComparisonRow(
                title=paper.metadata.title,
                note_path="",
                problem_definition=paper.problem_definition,
                method_category=paper.method_category,
                datasets_or_benchmarks=paper.datasets_or_benchmarks or UNKNOWN_BENCHMARK,
                strengths="；".join(paper.strengths),
                limitations="；".join(paper.weaknesses or paper.limitations),
            )
            for paper in papers
        ]
        overview = (
            f"这个专题围绕“{topic}”整理了 {len(papers)} 篇论文。"
            f"当前主线主要集中在：{dominant_categories}。"
            "这份索引页的作用不是代替原论文，而是先帮你建立阅读顺序和横向比较框架。"
        )
        why_these_papers = (
            "这些论文覆盖了这个方向里最常见的几类角色：综述、基线方法、结构升级和工程化变体。"
            "按这个集合来读，能先搞清楚问题是怎么被定义的，再理解后续论文到底是在改哪里。"
        )
        if role_counts:
            why_these_papers += " 这批论文中包括：" + "、".join(
                f"{_role_display(role)} {count} 篇" for role, count in role_counts.items()
            )
        selection_rationale = (
            "选文时优先保留近几年在该方向中被反复引用、方法演化关系清楚、"
            "并且能代表不同设计路线的论文。这样做的目标不是覆盖所有论文，"
            "而是先建立一个可长期扩展的阅读骨架。"
        )

        return TopicSummary(
            topic=topic,
            query=query,
            limit=len(papers),
            selection_rationale=selection_rationale,
            why_these_papers=why_these_papers,
            overview=overview,
            papers=papers,
            comparison_rows=comparison_rows,
            reading_order=reading_order,
        )

    def _summary_basis(self, parsed_paper: ParsedPaper) -> str:
        if parsed_paper.has_substantial_text:
            return FULL_TEXT_BASIS
        if parsed_paper.text.strip():
            return PARTIAL_TEXT_BASIS
        return ABSTRACT_ONLY_BASIS

    @staticmethod
    def _pick_section(section_map: dict[str, str], candidates: list[str]) -> str:
        for heading, body in section_map.items():
            if any(candidate in heading for candidate in candidates) and body:
                return body
        return ""

    def _compose_evidence(self, sources: list[str], keywords: list[str], fallback: str) -> str:
        selected = self._select_sentences(sources, keywords=keywords, limit=3)
        text = " ".join(selected).strip()
        return text or truncate_text(fallback, 500)

    @staticmethod
    def _select_sentences(sources: list[str], *, keywords: list[str], limit: int) -> list[str]:
        result: list[str] = []
        for source in sources:
            matches: list[tuple[int, str]] = []
            for sentence in split_sentences(source):
                lowered = sentence.lower()
                if lowered.startswith("figure ") or lowered.startswith("table "):
                    continue
                score = sum(1 for keyword in keywords if keyword in lowered)
                if score > 0:
                    matches.append((score, sentence.strip()))
            ranked = sorted(matches, key=lambda item: (-item[0], len(item[1])))
            for _, sentence in ranked:
                if sentence not in result:
                    result.append(sentence)
                if len(result) >= limit:
                    return result
        return result

    @staticmethod
    def _detect_task(text: str) -> str:
        lowered = text.lower()
        if "remote sensing" in lowered or "aerial" in lowered or "uav" in lowered:
            if "rotated" in lowered or "oriented" in lowered:
                return "遥感场景中的旋转目标检测"
            return "遥感图像目标检测"
        if "3d object detection" in lowered and (
            "autonomous driving" in lowered or "multi-view" in lowered
        ):
            return "自动驾驶中的多视角 3D 检测"
        if "bird's-eye-view" in lowered or "bev" in lowered:
            return "自动驾驶中的 BEV 感知"
        if "tracking" in lowered:
            return "自动驾驶中的目标跟踪"
        if "occupancy" in lowered:
            return "自动驾驶中的占据预测"
        if "rag" in lowered or "retrieval augmented generation" in lowered:
            return "检索增强生成"
        if "multimodal" in lowered or "vision-language" in lowered:
            return "多模态理解"
        return "通用机器学习任务"

    @staticmethod
    def _detect_method_focus(text: str) -> str:
        lowered = text.lower()
        if "3d-to-2d" in lowered:
            return "基于 3D-to-2D 查询的 Transformer 检测框架"
        if "quant" in lowered or "quantized" in lowered:
            return "面向部署优化的量化 Transformer 方案"
        if "position embedding" in lowered or "position-aware" in lowered:
            return "强调位置编码建模的 Transformer 方案"
        if "spatiotemporal" in lowered or "temporal" in lowered:
            return "强调时空融合的 Transformer 方案"
        if "sparse" in lowered:
            return "基于稀疏查询的高效检测方案"
        if "fusion" in lowered and "lidar" in lowered:
            return "面向多传感器融合的 Transformer 框架"
        if "bev" in lowered:
            return "围绕 BEV 表征构建的感知框架"
        if "oriented" in lowered or "rotated" in lowered:
            return "面向旋转框建模的 DETR 变体"
        if "uav" in lowered or "tiny object" in lowered or "small object" in lowered:
            return "面向无人机和小目标场景优化的检测框架"
        if "retrieval" in lowered or "rag" in lowered:
            return "围绕检索、过滤和生成校验设计的 RAG 流程"
        return "基于 Transformer 查询建模的感知方案"

    @staticmethod
    def _detect_challenges(text: str) -> str:
        lowered = text.lower()
        challenges: list[str] = []
        if "multi-view" in lowered or "multi-camera" in lowered:
            challenges.append("多视角信息对齐")
        if "bev" in lowered:
            challenges.append("BEV 表征构建与信息保持")
        if "temporal" in lowered or "tracking" in lowered:
            challenges.append("时序信息利用与误差累积")
        if "position embedding" in lowered or "position-aware" in lowered:
            challenges.append("空间位置编码设计")
        if "sparse" in lowered:
            challenges.append("稀疏查询的稳定性与召回")
        if "fusion" in lowered and "lidar" in lowered:
            challenges.append("多传感器对齐与融合成本")
        if "quant" in lowered or "quantized" in lowered:
            challenges.append("部署效率与精度折中")
        if "remote sensing" in lowered or "aerial" in lowered or "uav" in lowered:
            challenges.append("小目标密集分布与尺度变化")
        if "rotated" in lowered or "oriented" in lowered:
            challenges.append("旋转框角度建模")
        if "retrieval" in lowered or "rag" in lowered:
            challenges.append("检索噪声和答案幻觉")
        if not challenges:
            challenges.append("复杂场景下的稳健泛化")
        return "、".join(dedupe_preserve_order(challenges[:3]))

    def _build_method_breakdown(self, text: str) -> list[str]:
        lowered = text.lower()
        items: list[str] = []
        if "multi-view" in lowered or "multi-camera" in lowered:
            items.append("先提取多相机特征，再在统一空间里完成跨视角信息聚合。")
        if "query" in lowered:
            items.append("用 object query 或 BEV query 驱动检测解码，而不是先手工生成大量候选框。")
        if "position embedding" in lowered or "position-aware" in lowered:
            items.append("通过位置编码把 3D 几何先验注入查询，让模型更容易对齐空间位置。")
        if "bev" in lowered:
            items.append("显式构建 BEV 表征，方便后续检测、规划或占据预测共享同一表示。")
        if "temporal" in lowered or "tracking" in lowered:
            items.append("引入时序模块，让历史帧信息参与当前帧推理，提高稳定性。")
        if "sparse" in lowered:
            items.append("利用稀疏表示减少计算量，同时尽量保持召回率。")
        if "fusion" in lowered and "lidar" in lowered:
            items.append("融合相机和 LiDAR 等多传感器信号，提升几何感知能力。")
        if "rotated" in lowered or "oriented" in lowered:
            items.append("把目标方向或角度显式纳入预测头，解决遥感场景中的旋转框问题。")
        if "uav" in lowered or "tiny object" in lowered or "small object" in lowered:
            items.append("针对小目标场景增强高分辨率细节保留和多尺度特征利用。")
        if "retrieval" in lowered or "rag" in lowered:
            items.append("把查询重写、检索过滤和答案校验串成一个更稳的检索增强链路。")
        if "quant" in lowered or "quantized" in lowered:
            items.append("用量化或轻量化设计压缩部署成本，尽量少牺牲精度。")
        if not items:
            items.append("整体仍是编码器、查询和解码器三部分协同工作的端到端流程。")
        return dedupe_preserve_order(items)

    @staticmethod
    def _build_experiment_setup(*, benchmarks: str, metrics: str) -> list[str]:
        items = []
        if benchmarks and UNKNOWN_BENCHMARK not in benchmarks:
            items.append(f"主实验主要在 {benchmarks} 等数据集或基准上完成。")
        else:
            items.append("正文摘录里没有明确给出统一的数据集名称，建议回到实验章节核对主表。")
        if metrics:
            items.append(f"阅读结果时重点关注 {metrics} 等指标的变化。")
        items.append("先看主结果表，确认相对强基线提升了多少。")
        items.append("再看消融实验，确认收益到底来自哪个新增模块。")
        return items

    @staticmethod
    def _build_strengths(text: str, *, benchmarks: str) -> list[str]:
        lowered = text.lower()
        strengths: list[str] = []
        if any(keyword in lowered for keyword in ["outperform", "state-of-the-art", "sota"]):
            strengths.append("在公开基准上给出了有竞争力的结果。")
        if any(keyword in lowered for keyword in ["efficient", "real-time", "latency", "fast"]):
            strengths.append("同时考虑了效果和效率，具备一定工程落地价值。")
        if "temporal" in lowered or "tracking" in lowered:
            strengths.append("时序建模增强了输出稳定性。")
        if "fusion" in lowered or "multi-view" in lowered or "multi-camera" in lowered:
            strengths.append("跨视角或多模态信息融合能力较强。")
        if "remote sensing" in lowered or "aerial" in lowered or "uav" in lowered:
            strengths.append("对小目标、密集目标或复杂拍摄视角做了针对性优化。")
        if benchmarks and UNKNOWN_BENCHMARK not in benchmarks:
            strengths.append(f"覆盖了 {benchmarks} 等常见基准，方便横向比较。")
        if not strengths:
            strengths.append("问题定义清楚，方法设计具备延展性。")
        return dedupe_preserve_order(strengths)

    @staticmethod
    def _build_limitations(text: str, *, basis: str) -> list[str]:
        lowered = text.lower()
        limitations: list[str] = []
        if basis != FULL_TEXT_BASIS:
            limitations.append("当前总结并非完整通读全文，部分判断仍需要结合 PDF 原文复核。")
        if "camera-only" in lowered or "multi-view" in lowered or "multi-camera" in lowered:
            limitations.append("对标定质量、视角覆盖和遮挡情况仍然比较敏感。")
        if "temporal" in lowered or "tracking" in lowered:
            limitations.append("时序模块可能带来误差累积和更高推理延迟。")
        if "fusion" in lowered and "lidar" in lowered:
            limitations.append("多传感器系统对同步和标定要求更高。")
        if "quant" in lowered or "quantized" in lowered:
            limitations.append("量化方案可能在极端场景下损失部分精度。")
        if "remote sensing" in lowered or "aerial" in lowered or "uav" in lowered:
            limitations.append("遥感场景的跨数据集泛化和超密集目标召回通常仍是难点。")
        if not limitations:
            limitations.append("泛化能力、训练成本和长尾场景表现仍需要进一步核对。")
        return dedupe_preserve_order(limitations)

    @staticmethod
    def _build_key_findings(*, strengths: list[str], benchmarks: str, metrics: str) -> list[str]:
        findings: list[str] = []
        if strengths:
            findings.extend(strengths[:2])
        if benchmarks and UNKNOWN_BENCHMARK not in benchmarks:
            findings.append(f"建议重点对照 {benchmarks} 上与强基线的性能差距。")
        if metrics:
            findings.append(f"需要核对 {metrics} 等指标提升是否稳定，而不是只看单个最好结果。")
        return dedupe_preserve_order(findings)

    @staticmethod
    def _build_contributions(
        *,
        task_focus: str,
        method_focus: str,
        method_breakdown: list[str],
        benchmarks: str,
    ) -> list[str]:
        contributions = [f"围绕{task_focus}提出了{method_focus}。"]
        contributions.extend(method_breakdown[:2])
        if benchmarks and UNKNOWN_BENCHMARK not in benchmarks:
            contributions.append(f"在 {benchmarks} 等基准上给出了相对完整的实验验证。")
        return dedupe_preserve_order(contributions)

    @staticmethod
    def _infer_use_cases(text: str) -> list[str]:
        lowered = text.lower()
        cases: list[str] = []
        if "autonomous driving" in lowered or "3d object detection" in lowered:
            cases.append("适合自动驾驶中的环境感知、目标检测和 BEV 表征建模。")
        if "tracking" in lowered:
            cases.append("适合需要连续帧稳定输出的在线跟踪场景。")
        if "fusion" in lowered and "lidar" in lowered:
            cases.append("适合多传感器车端感知系统。")
        if "remote sensing" in lowered or "aerial" in lowered or "uav" in lowered:
            cases.append("适合遥感图像、无人机场景和小目标密集检测任务。")
        if "quant" in lowered or "quantized" in lowered:
            cases.append("适合资源受限的边缘部署场景。")
        if "rag" in lowered or "retrieval" in lowered:
            cases.append("适合企业知识库问答与检索增强生成系统。")
        if not cases:
            cases.append("适合作为同类方法设计与复现实验的参考起点。")
        return dedupe_preserve_order(cases)

    def _follow_up_advice(self, parsed_paper: ParsedPaper, basis: str) -> list[str]:
        advice: list[str] = []
        if basis != FULL_TEXT_BASIS:
            advice.append("建议回到 PDF 原文补看方法总图、主实验表和消融实验。")
        if parsed_paper.references_text:
            advice.append("可以顺着参考文献继续追前置工作和强基线。")
        advice.append("把模型结构、数据集和结果数字单独抄成自己的对比表，会更容易真正看懂。")
        advice.append("重点核对查询设计、特征表示和结果提升之间的因果关系。")
        return advice

    @staticmethod
    def _build_reading_path(parsed_paper: ParsedPaper) -> list[str]:
        preferred: list[str] = []
        for section in parsed_paper.sections:
            heading = section.heading.strip()
            lowered = heading.lower()
            if any(
                keyword in lowered
                for keyword in [
                    "introduction",
                    "method",
                    "approach",
                    "experiment",
                    "ablation",
                    "conclusion",
                ]
            ):
                preferred.append(f"优先阅读章节：{heading}")
        if preferred:
            return dedupe_preserve_order(preferred)
        return [
            "先看方法总图，确认输入、查询和输出分别是什么。",
            "再看位置编码、query 设计和特征表示是如何组织的。",
            "然后看主实验表，确认相比强基线提升了多少。",
            "最后看消融实验和局限性分析。",
        ]

    @staticmethod
    def _build_figure_reading_tips(text: str) -> list[str]:
        lowered = text.lower()
        tips = ["先看方法总图，确认特征流向、查询定义和预测头的位置。"]
        if "bev" in lowered:
            tips.append("重点看图里从图像到 BEV 的映射过程，以及 BEV token 如何更新。")
        if "query" in lowered or "detr" in lowered:
            tips.append("关注 query 的初始化方式，以及 decoder 如何把 query 变成最终预测。")
        if "temporal" in lowered or "tracking" in lowered:
            tips.append("留意历史帧特征怎样进入当前帧，以及是否使用缓存或递归设计。")
        if "quant" in lowered or "quantized" in lowered:
            tips.append("留意量化发生在骨干、编码器还是解码器上。")
        if "remote sensing" in lowered or "oriented" in lowered or "rotated" in lowered:
            tips.append(
                "重点看旋转框或小目标处理模块是在哪一层插入的，以及它如何提升密集目标识别。"
            )
        return dedupe_preserve_order(tips)

    @staticmethod
    def _build_citation(metadata: PaperMetadata) -> str:
        author_text = format_authors(metadata.authors)
        year = metadata.year or "n.d."
        identifier = metadata.arxiv_id or metadata.source_id
        return f"{author_text} ({year}). {metadata.title}. arXiv:{identifier}."

    @staticmethod
    def _classify_method(title: str, abstract: str) -> str:
        combined = f"{title} {abstract}".lower()
        if "survey" in combined or "review" in combined:
            return "综述 / 调研"
        if "benchmark" in combined or "evaluation" in combined:
            return "评测 / 基准"
        if "framework" in combined or "pipeline" in combined or "system" in combined:
            return "方法 / 框架"
        if "retrieval" in combined or "index" in combined or "memory" in combined:
            return "检索增强"
        if "training" in combined or "alignment" in combined or "fine-tun" in combined:
            return "训练 / 对齐"
        if "quant" in combined or "quantized" in combined:
            return "压缩 / 量化"
        return CORE_METHOD_LABEL

    @staticmethod
    def _classify_role(title: str, abstract: str) -> str:
        combined = f"{title} {abstract}".lower()
        if "survey" in combined or "review" in combined:
            return "survey"
        if "benchmark" in combined or "evaluation" in combined:
            return "benchmark"
        if "framework" in combined or "system" in combined:
            return "framework"
        if "dataset" in combined:
            return "dataset"
        return "core method"

    @staticmethod
    def _extract_benchmarks(text: str) -> str:
        hits = [name for name in KNOWN_BENCHMARKS if name.lower() in text.lower()]
        if hits:
            return "、".join(hits)

        dataset_keywords = ["dataset", "benchmark", "evaluate", "corpus"]
        for sentence in split_sentences(text):
            lowered = sentence.lower()
            if any(keyword in lowered for keyword in dataset_keywords):
                return truncate_text(sentence, 180)
        return UNKNOWN_BENCHMARK

    @staticmethod
    def _extract_metrics(text: str) -> str:
        hits = [name for name in METRIC_KEYWORDS if name.lower() in text.lower()]
        return "、".join(dedupe_preserve_order(hits))

    @staticmethod
    def _topic_sort_key(summary: PaperSummary) -> tuple[int, int, str]:
        role_rank = {
            "survey": 0,
            "benchmark": 1,
            "framework": 2,
            "dataset": 3,
            "core method": 4,
        }.get(summary.paper_role, 5)
        year = summary.metadata.year or 0
        return role_rank, year, summary.metadata.title.lower()


def _role_display(role: str) -> str:
    mapping = {
        "survey": "综述",
        "benchmark": "评测 / 基准",
        "framework": "框架",
        "dataset": "数据集",
        "core method": CORE_METHOD_LABEL,
    }
    return mapping.get(role, role or "未知")
