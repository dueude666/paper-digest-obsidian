from pathlib import Path

import pytest

from paper_digest.exceptions import ResearchProfileError
from paper_digest.research.profile import ResearchProfileLoader


def test_research_profile_loader_reads_upstream_compatible_yaml(tmp_path: Path) -> None:
    profile_path = tmp_path / "research_interests.yaml"
    profile_path.write_text(
        """research_domains:
  rag:
    keywords:
      - rag
      - retrieval augmented generation
    arxiv_categories:
      - cs.CL
      - cs.IR
    priority: 3
excluded_keywords:
  - survey
""",
        encoding="utf-8",
    )

    profile = ResearchProfileLoader().load(profile_path)

    assert profile.excluded_keywords == ["survey"]
    assert len(profile.research_domains) == 1
    assert profile.research_domains[0].name == "rag"
    assert profile.research_domains[0].priority == 3
    assert profile.research_domains[0].arxiv_categories == ["cs.CL", "cs.IR"]


def test_research_profile_loader_requires_non_empty_domains(tmp_path: Path) -> None:
    profile_path = tmp_path / "research_interests.yaml"
    profile_path.write_text("research_domains: {}\n", encoding="utf-8")

    with pytest.raises(ResearchProfileError):
        ResearchProfileLoader().load(profile_path)
