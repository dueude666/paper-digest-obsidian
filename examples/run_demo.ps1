$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
    .\.venv\Scripts\python -m pip install -U pip
    .\.venv\Scripts\python -m pip install -e .[dev]
}

$env:OBSIDIAN_VAULT_PATH = (Resolve-Path ".").Path + "\\vault"
$env:RESEARCH_PROFILE_PATH = (Resolve-Path ".\\examples\\research_interests.yaml").Path

.\.venv\Scripts\summarize-paper.exe "https://arxiv.org/abs/1706.03762" --topic transformers --vault "$env:OBSIDIAN_VAULT_PATH"
.\.venv\Scripts\recommend-daily.exe --top-n 5 --analyze-top-n 2 --vault "$env:OBSIDIAN_VAULT_PATH"
