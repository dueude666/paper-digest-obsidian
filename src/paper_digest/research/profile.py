"""Research interest profile loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from paper_digest.exceptions import ResearchProfileError
from paper_digest.models import ResearchDomain, ResearchProfile


class ResearchProfileLoader:
    """Load YAML research profiles compatible with the upstream workflow."""

    def load(self, path: Path) -> ResearchProfile:
        if not path.exists():
            raise ResearchProfileError(f"Research profile not found: {path}")

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as error:
            raise ResearchProfileError(
                f"Failed to parse research profile {path}: {error}"
            ) from error

        domains = self._parse_domains(raw)
        excluded_keywords = [
            str(keyword).strip()
            for keyword in raw.get("excluded_keywords", [])
            if str(keyword).strip()
        ]
        vault_path = raw.get("vault_path")
        return ResearchProfile(
            vault_path=Path(vault_path).expanduser() if vault_path else None,
            research_domains=domains,
            excluded_keywords=excluded_keywords,
        )

    @staticmethod
    def _parse_domains(raw: dict[str, Any]) -> list[ResearchDomain]:
        research_domains = raw.get("research_domains")
        if not isinstance(research_domains, dict) or not research_domains:
            raise ResearchProfileError(
                "Research profile must define a non-empty 'research_domains' mapping."
            )

        domains: list[ResearchDomain] = []
        for domain_name, config in research_domains.items():
            if not isinstance(config, dict):
                continue
            domains.append(
                ResearchDomain(
                    name=str(domain_name),
                    keywords=[
                        str(keyword).strip()
                        for keyword in config.get("keywords", [])
                        if str(keyword).strip()
                    ],
                    arxiv_categories=[
                        str(category).strip()
                        for category in config.get("arxiv_categories", [])
                        if str(category).strip()
                    ],
                    priority=int(config.get("priority", 1) or 1),
                )
            )

        if not domains:
            raise ResearchProfileError("No valid research domains found in the profile.")
        return domains
