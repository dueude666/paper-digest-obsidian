# Contributing

## Development setup

Create a virtual environment and install development dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .[dev]
```

Or use `uv`:

```bash
uv sync --extra dev
```

## Before opening a pull request

Run the local quality gates:

```powershell
.\.venv\Scripts\python -m black --check src tests
.\.venv\Scripts\python -m ruff check src tests
.\.venv\Scripts\pytest -q --basetemp=test-output\pytest_tmp_run --override-ini cache_dir=test-output\pytest_cache_run
.\.venv\Scripts\python -m build
```

## Contribution guidelines

- keep modules layered: source, fetcher, parser, summarizer, writer, CLI
- prefer explicit Pydantic models over loose dictionaries
- avoid hard-coding provider-specific behavior into the workflow layer
- keep network code mockable
- preserve Chinese-first Obsidian output unless a change is explicitly configurable
- add or update tests when behavior changes

## Pull request scope

Good pull requests are usually one of:

- new paper source integration
- parser extraction improvement
- summarization quality improvement
- Obsidian output and linking improvement
- test or packaging improvement

Avoid mixing unrelated refactors into a single pull request.
