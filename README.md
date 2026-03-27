# ai-sessions-salvager

將 ChatGPT / Claude 匯出 JSON 批次轉成每段對話一個 Markdown，並可選擇執行 LLM 分析（預設摘要或嚴格 salvage 模式）。另外也提供等級 A 對話蒐集工具，方便後續歸檔。

## Features
- Parse `chatgpt` / `claude` export JSON (`--format auto` supported)
- Write one `conv_<safe_id>.md` per conversation
- Convert-only mode (`--skip-analysis`) with no API calls required
- Batch call LLM API for either default summary schema or strict residue-salvage schema
- Supports **OpenAI** and **Anthropic (Claude)** as analysis providers
- Write one `conv_<safe_id>.analysis.json` per conversation
- Maintain `index.csv`
- Supports retries + resume/force
- Collect only route `A` results and merge analysis + conversation into standalone Markdown (`collect_grade_a.py`)

## Requirements
- Python 3.10+
- API key in env var — only required when analysis is enabled:
  - `OPENAI_API_KEY` for `--provider openai` (default)
  - `ANTHROPIC_API_KEY` for `--provider anthropic`

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

OpenAI:
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

Anthropic Claude:
```bash
python convert_and_analyze.py \
  --input export.json \
  --format auto \
  --provider anthropic \
  --model claude-sonnet-4-6 \
  --output-root ./output \
  --max-concurrency 5 \
  --retry 3 \
  --resume
```

### Salvage analysis schema

OpenAI:
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

Anthropic Claude:
```bash
python convert_and_analyze.py \
  --input export.json \
  --format auto \
  --provider anthropic \
  --model claude-sonnet-4-6 \
  --analysis-schema salvage \
  --output-root ./output \
  --resume
```

### 只蒐集 route `A` 結果並合併輸出

```bash
python collect_grade_a.py \
  --input-root ./output \
  --output-dir ./grade_a
```

此工具會掃描 `--input-root` 下的 `*.analysis.json`，只保留 `route_recommendation == "A"` 的對話，並把分析摘要 + 原始對話 `.md` 合併後輸出到 `--output-dir`。

## Salvage mode outputs JSON fields
- `topic`
- `valuable_residuals`
- `drift_point`
- `next_steps`
- `route_recommendation` (`A|B|C|D`)
- `initial_route_recommendation`
- `final_route_recommendation`
- `calibration_applied`
- `calibration_confidence`
- `calibration_reason`
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
  - B does **not** require high completeness; if the salvageable residual is already work-system-worthy, it can be B.
  - B must also **not** be explicitly judged as "not yet ready for direct work-system use"; if it is only worth excerpting/partial retention, it should be `C`.
- `C`: only partial residual value (e.g., one salvageable naming/judgment/sentence), not enough for high-grade preservation
- `D`: overall not worth saving (low information density, routine Q&A/translation/sorting/log-like content)

Salvage now uses a **two-stage hybrid flow**:

1. first-pass extraction (existing salvage JSON extraction + hard guards)
2. selective second-pass route calibration (LLM judge only for ambiguous `B/C` boundary cases)

The second pass does **not** re-summarize or re-extract the conversation. It only calibrates final route recommendation from compact first-pass JSON (+ short excerpt when needed). Clear `A` and hard-rule `D` cases skip second pass to avoid unnecessary extra model calls.

Seeing more `C/D` than earlier versions is expected behavior, not a bug.

## Output files
(Generated in `--output-root`, default `.`)

- `conv_<safe_id>.md`
- `conv_<safe_id>.analysis.json` (when analysis is enabled)
- `index.csv`
  - includes `route_recommendation`, `initial_route_recommendation`, `final_route_recommendation`, `calibration_applied`, `calibration_confidence`, `verdict`, `valuable_residual_count`, `next_steps_count` for easier distribution review
  - append behavior: `convert_and_analyze.py` `write_index_row()` opens `index.csv` with append mode (`"a"`), so repeated runs add rows instead of auto-overwriting or deduplicating.
  - quick locator for maintainers: `write_index_row()` defines index fields as `id,title,source,md_file,analysis_file,route_recommendation,initial_route_recommendation,final_route_recommendation,calibration_applied,calibration_confidence,verdict,valuable_residual_count,next_steps_count,primary_text,summary,tags,status,error`.
  - for clean single-run results, remove/reset old `index.csv` first or use a fresh `--output-root`.

若使用 `collect_grade_a.py`，會在 `--output-dir` 額外產生：

- `conv_<safe_id>.md`（合併檔）
  - 前段：分析摘要（route、topic、verdict、drift point、residuals、next steps、校準資訊）
  - 後段：原始對話內容

## Notes
- `--provider` 支援 `openai`（預設）和 `anthropic`；`--api-key-env` 預設會依 provider 自動選擇對應的環境變數名稱。
- `--model` is required unless `--skip-analysis` is used.
- `--analysis-schema` supports `default|salvage` (default: `default`).
- If `--resume` is enabled and analysis file exists, that conversation is skipped unless `--force` is provided.
- `--sample N` 可只處理前 N 筆對話（方便抽樣測試流程）。
- For a clean one-off run, clear/delete old `index.csv` first, or write to a separate `--output-root`.
- `collect_grade_a.py` 需要同時存在 `conv_<id>.analysis.json` 與對應 `conv_<id>.md`；若缺少 `.md` 會略過該筆並輸出警告。

## Privacy/Safety
- 轉換出的 `conv_<safe_id>.md`、`conv_<safe_id>.analysis.json` 與 `index.csv` 可能包含敏感資訊（例如個資、內部討論、API 片段）。
- 建議把輸出寫到獨立資料夾（例如 `--output-root ./output`），並確保該資料夾與輸出檔案不提交到版本控制。
- 本 repo 已提供 `.gitignore` 預設忽略上述輸出與 `output/` 目錄，請在提交前再次確認。
