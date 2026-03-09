"""Application settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Runtime settings loaded from environment or CLI defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    obsidian_vault_path: Path | None = Path("./vault")
    literature_dir_name: str = "文献库"
    daily_dir_name: str = "每日推荐"
    papers_dir_name: str = "论文笔记"
    full_text_dir_name: str = "论文全文"
    pdf_dir_name: str = "原文PDF"
    assets_dir_name: str = "图片素材"
    cache_dir: Path = Path("./.cache/paper-digest")
    default_topic: str = "未整理"
    log_level: str = "INFO"
    auto_link_existing_notes: bool = False
    default_daily_top_n: int = 10
    default_daily_analyze_top_n: int = 3
    research_profile_path: Path | None = None

    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3
    http_retry_backoff_seconds: float = 1.5
    user_agent: str = "paper-digest/0.1.0"

    arxiv_api_url: str = "https://export.arxiv.org/api/query"
    semantic_scholar_api_url: str = "https://api.semanticscholar.org/graph/v1/paper/search"
    semantic_scholar_fields: str = (
        "title,abstract,publicationDate,citationCount,influentialCitationCount,"
        "url,authors,externalIds,openAccessPdf,year"
    )
    semantic_scholar_request_interval_seconds: float = 1.5

    summary_backend: Literal["heuristic", "openai-compatible"] = "heuristic"
    summary_audience: Literal["technical", "beginner"] = "beginner"
    summary_detail_level: Literal["standard", "detailed"] = "detailed"
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 90.0

    overwrite_strategy: Literal["overwrite", "skip", "suffix"] = "overwrite"

    @field_validator(
        "obsidian_vault_path",
        "cache_dir",
        "research_profile_path",
        mode="before",
    )
    @classmethod
    def _normalize_path(cls, value: Path | str | None) -> Path | None:
        if value in (None, ""):
            return None
        return Path(value).expanduser()

    @field_validator(
        "literature_dir_name",
        "daily_dir_name",
        "papers_dir_name",
        "full_text_dir_name",
        "pdf_dir_name",
        "assets_dir_name",
    )
    @classmethod
    def _validate_dir_name(cls, value: str, info) -> str:
        value = value.strip()
        defaults = {
            "literature_dir_name": "文献库",
            "daily_dir_name": "每日推荐",
            "papers_dir_name": "论文笔记",
            "full_text_dir_name": "论文全文",
            "pdf_dir_name": "原文PDF",
            "assets_dir_name": "图片素材",
        }
        return value or defaults[info.field_name]

    def vault_path(self, override: Path | None = None) -> Path | None:
        base = override or self.obsidian_vault_path
        return None if base is None else base.expanduser()

    def literature_root(self, override: Path | None = None) -> Path | None:
        vault = self.vault_path(override=override)
        return None if vault is None else vault / self.literature_dir_name

    def daily_root(self, override: Path | None = None) -> Path | None:
        literature_root = self.literature_root(override=override)
        return None if literature_root is None else literature_root / self.daily_dir_name

    def resolved_research_profile_path(self, override: Path | None = None) -> Path | None:
        if override is not None:
            return override.expanduser()
        if self.research_profile_path is not None:
            return self.research_profile_path
        vault = self.vault_path()
        if vault is None:
            return None
        return vault / "99_System" / "Config" / "research_interests.yaml"
