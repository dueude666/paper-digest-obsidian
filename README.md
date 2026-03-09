# paper-digest-obsidian

`paper-digest-obsidian` is a local Python workflow for searching arXiv papers, downloading PDFs, extracting text, generating structured summaries, and writing Obsidian-friendly Markdown notes into your vault.

Chinese documentation: [README.zh-CN.md](README.zh-CN.md)

The project keeps the useful parts of the `evil-read-arxiv` workflow, but rewrites them as a maintainable local Python application for Codex-style usage:

- layered architecture instead of ad-hoc scripts
- Typer CLI for repeatable workflows
- Pydantic models for data contracts
- resumable caching for metadata and PDFs
- fallback-first summarization design
- Obsidian-oriented output with stable paths and wikilinks
- optional OpenAI-compatible summarization backend

## What it does

- summarize a single arXiv paper from URL or title
- summarize a topic with top-N paper notes plus an index page
- sync the original PDF into your vault for direct reading in Obsidian
- optionally export a full-paper extracted note with the original PDF embedded
- extract paper images into Obsidian assets folders
- build daily recommendation digests from a research profile
- scan and link existing Obsidian notes
- keep the output Chinese-first by default, including folder names and note templates

## Current scope

Implemented now:

- arXiv metadata lookup
- arXiv PDF download
- PDF text extraction with `PyMuPDF`, plus `pdfplumber` fallback
- rule-based structured summaries
- OpenAI-compatible overlay summarizer
- Obsidian paper notes, topic index pages, daily digests
- local caching
- test suite, linting, packaging, CI

Planned extensions:

- richer Semantic Scholar / OpenAlex integration
- stronger citation analysis and dataset extraction
- concept pages and dataset hub pages for denser Obsidian graph views
- more robust image/table extraction

## Installation

### Option A: `uv` (recommended)

```bash
uv sync --extra dev
```

### Option B: `venv + pip`

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .[dev]
```

## Quick start

1. Copy the environment template:

```powershell
Copy-Item .env.example .env
```

2. Edit `.env`:

```env
OBSIDIAN_VAULT_PATH=F:/YourObsidianVault
SUMMARY_BACKEND=heuristic
SUMMARY_AUDIENCE=beginner
SUMMARY_DETAIL_LEVEL=detailed
```

3. Run a health check:

```powershell
.\.venv\Scripts\paper-digest.exe doctor
```

4. Summarize one paper:

```powershell
.\.venv\Scripts\summarize-paper.exe "https://arxiv.org/abs/1706.03762" --topic transformer
```

5. Summarize a topic:

```powershell
.\.venv\Scripts\summarize-topic.exe "retrieval augmented generation" --limit 10 --topic rag
```

## CLI commands

### Summarize one paper by arXiv URL or id

```powershell
.\.venv\Scripts\summarize-paper.exe "https://arxiv.org/abs/2501.01234"
.\.venv\Scripts\summarize-paper.exe "2501.01234"
```

### Summarize one paper by title

```powershell
.\.venv\Scripts\summarize-paper.exe --title "Attention Is All You Need"
```

### Summarize a topic

```powershell
.\.venv\Scripts\summarize-topic.exe "autonomous driving detr" --limit 10 --topic 自动驾驶detr
```

### Read the original paper PDF in Obsidian

```powershell
.\.venv\Scripts\view-paper.exe "https://arxiv.org/abs/1706.03762" --topic transformer
```

This command syncs the raw PDF into:

```text
<vault>/文献库/<topic>/原文PDF/<paper-slug>.pdf
```

### Export an extracted full-paper note

```powershell
.\.venv\Scripts\view-paper-note.exe "https://arxiv.org/abs/1706.03762" --topic transformer
```

### Rebuild topic indexes

```powershell
.\.venv\Scripts\paper-digest.exe reindex --topic 自动驾驶detr
```

### Daily recommendations

```powershell
.\.venv\Scripts\recommend-daily.exe --top-n 10 --analyze-top-n 3
```

### Search existing notes

```powershell
.\.venv\Scripts\search-notes.exe "vector database"
```

### Extract paper images only

```powershell
.\.venv\Scripts\extract-images.exe "https://arxiv.org/abs/1706.03762" --topic transformer
```

## Output layout

By default, notes are written into Chinese-named Obsidian folders:

```text
<vault>/
  文献库/
    <topic-slug>/
      index.md
      论文笔记/
        <paper-slug>.md
      原文PDF/
        <paper-slug>.pdf
      论文全文/
        <paper-slug>.md
      图片素材/
        <paper-slug>/
```

These folder names are configurable through `.env`.

## Example paper note structure

Each paper note includes:

- YAML frontmatter
- one-sentence summary
- beginner-friendly “read this first” block
- research context and problem statement
- method breakdown
- experiment setup
- main results
- contributions
- limitations
- suggested reading path
- citation
- image embeds when available

The full-paper note includes:

- a vault-synced local PDF copy
- inline Obsidian PDF embed
- extracted abstract
- extracted sections when parsing succeeds
- references excerpt and parser warnings when available

If you only want the original paper itself, use `view-paper`. If you want the extracted full-text helper note, use `view-paper-note`.

The default output style is optimized for readers who want:

- what model was used
- what the paper actually built
- which datasets were used
- how the reported results compare

## OpenAI-compatible summarization

The default backend is heuristic and works offline after download.

If you want stronger Chinese explanations, switch to the OpenAI-compatible backend:

```env
SUMMARY_BACKEND=openai-compatible
SUMMARY_AUDIENCE=beginner
SUMMARY_DETAIL_LEVEL=detailed
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your_api_key
LLM_MODEL=gpt-5.2
```

Design principle:

- heuristic summary always exists as the baseline
- LLM output only overlays fields that were returned successfully
- if the LLM call fails, the workflow falls back to heuristic mode instead of breaking

## Architecture

```text
src/paper_digest/
  cli/                 Typer entrypoints
  knowledge/           Existing-note indexing and wikilinks
  obsidian_writer/     Markdown rendering and vault writes
  paper_fetcher/       Metadata fetch, PDF download, cache
  paper_images/        PDF image extraction
  paper_parser/        PDF text extraction
  paper_sources/       arXiv / Semantic Scholar / OpenAlex adapters
  recommendation/      Daily paper recommendation workflow
  research/            Research-profile loading
  services/            Workflow orchestration
  summarizer/          Heuristic + OpenAI-compatible summarizers
```

## Development

Run formatting, linting, and tests:

```powershell
.\.venv\Scripts\python -m black --check src tests
.\.venv\Scripts\python -m ruff check src tests
.\.venv\Scripts\pytest -q --basetemp=test-output\pytest_tmp_run --override-ini cache_dir=test-output\pytest_cache_run
```

Build a distribution package:

```powershell
.\.venv\Scripts\python -m build
```

## Why this project exists

This repository is intended for people who want a paper-reading workflow that is:

- local-first
- Obsidian-native
- easy to inspect and extend
- robust enough to keep using after the first demo

The target is not a 1:1 clone of any upstream workflow. The target is a clean engineering baseline that can continue to grow.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
