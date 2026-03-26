# ai-sessions-salvager

Batch-convert official ChatGPT/Claude export JSON into one markdown file per conversation, then run LLM summary/tag extraction and save outputs in the repository root.

## Features
- Parse `chatgpt` / `claude` export JSON (`--format auto` supported)
- Write one `conv_<id>.md` per conversation
- Batch call LLM API for summary/tags
- Write one `conv_<id>.analysis.json` per conversation
- Maintain `index.csv`
- Supports retries + resume/force

## Requirements
- Python 3.10+
- OpenAI-compatible API key in env var (default `OPENAI_API_KEY`)

## Usage

### Bash / zsh
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

### PowerShell
```powershell
python .\convert_and_analyze.py `
  --input .\export.json `
  --format auto `
  --provider openai `
  --model gpt-4.1-mini `
  --output-root . `
  --max-concurrency 5 `
  --retry 3 `
  --resume
```

PowerShell does not provide `head` by default. Use:
```powershell
python .\convert_and_analyze.py --help | Select-Object -First 20
```

## Output files (in `--output-root`, default `.`)
- `conv_<safe_id>.md`
- `conv_<safe_id>.analysis.json`
- `index.csv`

## Notes
- Current implementation supports `provider=openai`.
- If `--resume` is enabled and analysis file exists, that conversation is skipped unless `--force` is provided.
- You can validate conversion without API calls via `--skip-analysis`.
- `--model` is only required when analysis is enabled (i.e., not using `--skip-analysis`).
