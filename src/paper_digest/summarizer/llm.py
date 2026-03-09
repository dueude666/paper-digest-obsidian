"""Optional OpenAI-compatible summarization backend."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from paper_digest.config import AppSettings
from paper_digest.exceptions import ConfigurationError, NetworkError
from paper_digest.http import HttpClientProtocol
from paper_digest.models import PaperSummary, ParsedPaper, TopicSummary
from paper_digest.summarizer.base import SummaryEngine
from paper_digest.summarizer.heuristic import HeuristicSummarizer
from paper_digest.summarizer.prompts import build_paper_summary_prompt, build_topic_summary_prompt

LOGGER = logging.getLogger(__name__)

_STRING_FIELDS = {
    "summary_basis",
    "one_sentence",
    "research_context",
    "research_problem",
    "problem_evidence",
    "core_method",
    "method_evidence",
    "main_results",
    "results_evidence",
    "citation",
    "problem_definition",
    "method_category",
    "datasets_or_benchmarks",
    "paper_role",
}

_LIST_FIELDS = {
    "method_breakdown",
    "experiment_setup",
    "key_findings",
    "figure_reading_tips",
    "contributions",
    "limitations",
    "use_cases",
    "follow_up_advice",
    "reading_path",
    "short_overview",
    "strengths",
    "weaknesses",
}

_ROLE_MAPPING = {
    "survey": "survey",
    "综述": "survey",
    "benchmark": "benchmark",
    "评测": "benchmark",
    "评测 / 基准": "benchmark",
    "framework": "framework",
    "框架": "framework",
    "dataset": "dataset",
    "数据集": "dataset",
    "core method": "core method",
    "核心方法": "core method",
}


class OpenAICompatibleSummarizer(SummaryEngine):
    """Use an OpenAI-compatible chat completion endpoint with heuristic fallback."""

    def __init__(self, settings: AppSettings, http_client: HttpClientProtocol):
        self._settings = settings
        self._http = http_client
        self._fallback = HeuristicSummarizer()

    def summarize_paper(self, parsed_paper: ParsedPaper) -> PaperSummary:
        heuristic_summary = self._fallback.summarize_paper(parsed_paper)
        try:
            payload = self._chat_completion(
                build_paper_summary_prompt(
                    parsed_paper,
                    baseline_summary=heuristic_summary,
                    audience=self._settings.summary_audience,
                    detail_level=self._settings.summary_detail_level,
                )
            )
            normalized = self._normalize_paper_payload(payload)
            return heuristic_summary.model_copy(update=normalized)
        except (
            ConfigurationError,
            NetworkError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            LOGGER.warning("LLM summarization failed, falling back to heuristic mode: %s", error)
            return heuristic_summary.model_copy(
                update={
                    "warnings": [
                        *heuristic_summary.warnings,
                        f"LLM summarization failed and fell back to heuristic mode: {error}",
                    ]
                }
            )

    def summarize_topic(self, topic: str, query: str, papers: list[PaperSummary]) -> TopicSummary:
        heuristic_topic = self._fallback.summarize_topic(topic=topic, query=query, papers=papers)
        try:
            payload = self._chat_completion(
                build_topic_summary_prompt(
                    topic=topic,
                    query=query,
                    papers=papers,
                    baseline_summary=heuristic_topic,
                    audience=self._settings.summary_audience,
                    detail_level=self._settings.summary_detail_level,
                )
            )
            return heuristic_topic.model_copy(update=self._normalize_topic_payload(payload))
        except (
            ConfigurationError,
            NetworkError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            LOGGER.warning(
                "LLM topic summarization failed, using heuristic topic summary: %s", error
            )
            return heuristic_topic

    def _chat_completion(self, prompt: str) -> dict[str, Any]:
        if not self._settings.llm_base_url or not self._settings.llm_model:
            raise ConfigurationError(
                "LLM_BASE_URL and LLM_MODEL are required for openai-compatible mode."
            )

        url = self._settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = (
            self._settings.llm_api_key.get_secret_value()
            if self._settings.llm_api_key is not None
            else None
        )
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        response = self._http.post_json(
            url,
            headers=headers,
            json_body={
                "model": self._settings.llm_model,
                "temperature": 0.1,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a patient Chinese research teacher. "
                            "Return exactly one JSON object and nothing else."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
        )
        content = response["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str):
            raise ValueError("Unexpected content payload from LLM response.")
        return _load_json_block(content)

    @staticmethod
    def _normalize_paper_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}

        for field_name in _STRING_FIELDS:
            value = payload.get(field_name)
            if isinstance(value, str) and value.strip():
                normalized[field_name] = value.strip()

        for field_name in _LIST_FIELDS:
            items = _as_list(payload.get(field_name))
            if items:
                normalized[field_name] = items

        if "paper_role" in normalized:
            normalized_role = _ROLE_MAPPING.get(normalized["paper_role"].strip().lower())
            if normalized_role is None:
                normalized.pop("paper_role", None)
            else:
                normalized["paper_role"] = normalized_role

        return normalized

    @staticmethod
    def _normalize_topic_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for field_name in ("selection_rationale", "why_these_papers", "overview"):
            value = payload.get(field_name)
            if isinstance(value, str) and value.strip():
                normalized[field_name] = value.strip()

        reading_order = _as_list(payload.get("reading_order"))
        if reading_order:
            normalized["reading_order"] = reading_order
        return normalized


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _load_json_block(content: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    json_text = match.group(0) if match else content
    payload = json.loads(json_text)
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object from LLM response.")
    return payload
