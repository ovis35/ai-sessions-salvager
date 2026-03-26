# ai-sessions-salvager

Batch-convert official ChatGPT/Claude export JSON into one markdown file per conversation, then optionally run LLM analysis and save outputs in the repository root.

## Features
- Parse `chatgpt` / `claude` export JSON (`--format auto` supported)
- Write one `conv_<id>.md` per conversation
- Convert-only mode (`--skip-analysis`) with no API calls required
- Batch call LLM API for either default summary schema or strict residue-salvage schema
- Write one `conv_<id>.analysis.json` per conversation
- Maintain `index.csv`
- Supports retries + resume/force

## Requirements
- Python 3.10+
- OpenAI-compatible API key in env var (default `OPENAI_API_KEY`) only when analysis is enabled

## Development

### 1) Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) Install development dependencies

```bash
python -m pip install --upgrade pip
python -m pip install tox
```

### 3) Run tests

```bash
python -m unittest discover -s tests -p "test_*.py"
# or
python -m tox
```

## Usage

### Convert-only mode (no model/API key required)

```bash
python convert_and_analyze.py \
  --input export.json \
  --format auto \
  --output-root ./output \
  --skip-analysis
```

### Default analysis schema (summary/tags/language/quality_score)

```bash
python convert_and_analyze.py \
  --input export.json \
  --format auto \
  --provider openai \
  --model gpt-4.1-mini \
  --output-root ./output \
  --max-concurrency 5 \
  --retry 3 \
  --resume
```

### Salvage analysis schema

```bash
python convert_and_analyze.py \
  --input export.json \
  --format auto \
  --provider openai \
  --model gpt-4.1-mini \
  --analysis-schema salvage \
  --output-root ./output \
  --resume
```

## Salvage mode outputs JSON fields
- `topic`
- `valuable_residuals`
- `drift_point`
- `next_steps`
- `route_recommendation` (`A|B|C|D`)
- `verdict`

## Salvage mode behavior
Salvage mode is intentionally strict residue salvage, not generic summarization (and stricter than before):

- prefer omission over over-inclusion
- avoid flattery or beautification
- keep only genuinely valuable residuals
- default to lower ratings when uncertain (`C/D` over `A/B`)

Route semantics in salvage mode:

- `A`: high-value reusable knowledge/frameworks that are worth preserving as durable principles or models
- `B`: clear execution value that should enter project/spec/task/decision records
- `C`: only partial residual value (e.g., one salvageable naming/judgment/sentence), not enough for high-grade preservation
- `D`: overall not worth saving (low information density, routine Q&A/translation/sorting/log-like content)

Seeing more `C/D` than earlier versions is expected behavior, not a bug.

## Output files
(Generated in `--output-root`, default `.`)

- `conv_<safe_id>.md`
- `conv_<safe_id>.analysis.json` (when analysis is enabled)
- `index.csv`
  - includes `route_recommendation`, `verdict`, `valuable_residual_count`, `next_steps_count` for easier distribution review
  - written by `write_index_row()` in append mode; existing rows are not automatically deduplicated or overwritten
  - header/columns align with `id,title,source,md_file,analysis_file,...` in `convert_and_analyze.py` for quick cross-reference

## Notes
- Current implementation supports `provider=openai`.
- `--model` is required unless `--skip-analysis` is used.
- `--analysis-schema` supports `default|salvage` (default: `default`).
- If `--resume` is enabled and analysis file exists, that conversation is skipped unless `--force` is provided.
- For a clean one-off run, clear/delete old `index.csv` first, or write to a separate `--output-root`.

## Privacy/Safety
- 轉換出的 `conv_*.md`、`conv_*.analysis.json` 與 `index.csv` 可能包含敏感資訊（例如個資、內部討論、API 片段）。
- 建議把輸出寫到獨立資料夾（例如 `--output-root ./output`），並確保該資料夾與輸出檔案不提交到版本控制。
- 本 repo 已提供 `.gitignore` 預設忽略上述輸出與 `output/` 目錄，請在提交前再次確認。
