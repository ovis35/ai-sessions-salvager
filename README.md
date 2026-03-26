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

## Usage

### Convert-only mode (no model/API key required)

```bash
python convert_and_analyze.py \
  --input export.json \
  --format auto \
  --output-root . \
  --skip-analysis
```

### Default analysis schema (`summary/tags/language/quality_score`)

```bash
python convert_and_analyze.py \
  --input export.json \
  --format auto \
  --provider openai \
  --model gpt-4.1-mini \
  --output-root . \
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
  --output-root . \
  --resume
```

Salvage mode outputs JSON fields:
- `topic`
- `valuable_residuals`
- `drift_point`
- `next_steps`
- `route_recommendation` (`A|B|C|D`)
- `verdict`

Salvage mode is intentionally strict residue salvage, not generic summarization:
- prefer omission over over-inclusion
- avoid flattery/beautification
- keep only genuinely valuable residuals

## Output files (in `--output-root`, default `.`)
- `conv_<safe_id>.md`
- `conv_<safe_id>.analysis.json` (when analysis is enabled)
- `index.csv`

## Notes
- Current implementation supports `provider=openai`.
- `--model` is required unless `--skip-analysis` is used.
- `--analysis-schema` supports `default|salvage` (default: `default`).
- If `--resume` is enabled and analysis file exists, that conversation is skipped unless `--force` is provided.
