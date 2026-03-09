"""Auto-link markdown content to existing Obsidian notes."""

from __future__ import annotations

import re

from paper_digest.knowledge.common_words import COMMON_WORDS
from paper_digest.models import NoteIndex


class MarkdownAutoLinker:
    """Replace matched keywords with Obsidian wikilinks."""

    def link(
        self, *, content: str, note_index: NoteIndex, exclude_paths: set[str] | None = None
    ) -> str:
        exclude_paths = exclude_paths or set()
        lines = content.splitlines()
        linked_lines: list[str] = []
        in_code_block = False
        in_frontmatter = False
        frontmatter_seen = 0

        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                frontmatter_seen += 1
                in_frontmatter = frontmatter_seen == 1
                if frontmatter_seen == 2:
                    in_frontmatter = False
                linked_lines.append(line)
                continue
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                linked_lines.append(line)
                continue
            if in_frontmatter or in_code_block or stripped.startswith("#"):
                linked_lines.append(line)
                continue
            if "[[" in line or "](" in line or "![" in line:
                linked_lines.append(line)
                continue
            linked_lines.append(
                self._link_line(line=line, note_index=note_index, exclude_paths=exclude_paths)
            )

        return "\n".join(linked_lines)

    def _link_line(self, *, line: str, note_index: NoteIndex, exclude_paths: set[str]) -> str:
        result = line
        for keyword in sorted(note_index.keyword_to_notes, key=len, reverse=True):
            if keyword in COMMON_WORDS or len(keyword) < 3:
                continue
            note_paths = [
                path for path in note_index.keyword_to_notes[keyword] if path not in exclude_paths
            ]
            if not note_paths:
                continue
            pattern = r"(?<![\w/-])" + re.escape(keyword) + r"(?![\w/-])"
            if not re.search(pattern, result, flags=re.IGNORECASE):
                continue
            target = _note_target(note_paths[0])
            result = re.sub(
                pattern,
                lambda match, target=target: f"[[{target}|{match.group(0)}]]",
                result,
                flags=re.IGNORECASE,
            )
        return result


def _note_target(path: str) -> str:
    return path[:-3] if path.endswith(".md") else path
