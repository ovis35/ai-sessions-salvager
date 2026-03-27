# ai-sessions-salvager

`ai-sessions-salvager` 是一個以 **Python 3.10+** 撰寫的批次工具，用來把 **ChatGPT / Claude 匯出 JSON** 轉成可閱讀、可歸檔的 Markdown，並可選擇呼叫 LLM 進行分析（一般摘要模式或嚴格 salvage 模式）。此外，專案也提供 `collect_grade_a.py`，可把 `route_recommendation == A` 的結果再整理成可直接保存的合併檔。

---

## 1. 核心能力總覽

- 支援輸入格式：`chatgpt`、`claude`，也支援 `--format auto` 自動判斷。  
- 產出每段對話一份 Markdown：`conv_<safe_id>.md`。  
- 可選擇只轉檔（`--skip-analysis`），不需任何 API Key。  
- 可呼叫 LLM 分析並輸出 `conv_<safe_id>.analysis.json`。  
- 分析 Provider 支援：`openai`、`anthropic`。  
- 維護 `index.csv`（以 conversation `id` upsert，重跑不會累積重複列）。  
- 提供 `--resume` / `--force` / `--retry` / `--max-concurrency` 等批次控制。  
- 支援 `--dry-run`，可估算 API 呼叫數與費用。  
- salvage 模式具備「第一階段抽取 + 第二階段校準」機制，降低過度高評。  
- 提供 `collect_grade_a.py`，只蒐集 A 級結果並合併分析與原文。

---

## 2. 專案結構

```text
.
├── convert_and_analyze.py      # 主程式：轉檔 + 分析 + index 維護
├── collect_grade_a.py          # 後處理：只蒐集 route A 並合併輸出
├── marker_lexicon.yaml         # semantic marker 詞彙設定（實際內容為 JSON）
├── tests/
│   ├── test_salvage_logic.py   # salvage 邏輯與 CLI 行為測試
│   └── test_collect_grade_a.py # A 級蒐集與 markdown 合併測試
├── pyproject.toml              # Python 專案設定 + tox 測試設定
└── README.md
```

---

## 3. 執行需求

- Python `>= 3.10`
- 若啟用分析（未使用 `--skip-analysis`）：
  - OpenAI：設定 `OPENAI_API_KEY`
  - Anthropic：設定 `ANTHROPIC_API_KEY`

> `--api-key-env` 可覆寫預設環境變數名稱；salvage 第二階段也可用 `--second-pass-api-key-env` 指定。

---

## 4. 安裝與開發

### 4.1 建立虛擬環境

```bash
python -m venv .venv
source .venv/bin/activate
```

### 4.2 安裝測試工具

```bash
python -m pip install --upgrade pip
python -m pip install tox
```

### 4.3 執行測試

```bash
python -m unittest discover -s tests -p "test_*.py"
# 或
python -m tox
```

---

## 5. 快速開始

## 5.1 只轉檔（不分析，不需 API）

```bash
python convert_and_analyze.py \
  --input ./export.json \
  --format auto \
  --output-root ./output \
  --skip-analysis
```

## 5.2 一般分析模式（default schema）

### OpenAI

```bash
python convert_and_analyze.py \
  --input ./export.json \
  --format auto \
  --provider openai \
  --model gpt-4.1-mini \
  --output-root ./output \
  --max-concurrency 5 \
  --retry 3 \
  --resume
```

### Anthropic

```bash
python convert_and_analyze.py \
  --input ./export.json \
  --format auto \
  --provider anthropic \
  --model claude-sonnet-4-6 \
  --output-root ./output \
  --max-concurrency 5 \
  --retry 3 \
  --resume
```

## 5.3 salvage 模式（嚴格殘值打撈）

```bash
python convert_and_analyze.py \
  --input ./export.json \
  --format auto \
  --provider openai \
  --model gpt-4.1-mini \
  --analysis-schema salvage \
  --output-root ./output \
  --resume
```

> 若要指定第二階段校準模型，可加上：
> `--second-pass-provider`、`--second-pass-model`（可與第一階段不同 provider/model）。

## 5.4 Dry-run（只估算，不落地）

```bash
python convert_and_analyze.py \
  --input ./export.json \
  --format auto \
  --provider openai \
  --model gpt-4.1-mini \
  --analysis-schema salvage \
  --dry-run
```

可搭配：

- `--estimate-input-tokens`（預設 `2500`）
- `--estimate-output-tokens`（預設 `500`）
- `--estimate-second-pass-ratio`（預設 `0.25`，僅影響 salvage 估算）
- `--price-input-per-1m` / `--price-output-per-1m`（覆寫內建價格）

## 5.5 蒐集 A 級對話並合併輸出

```bash
python collect_grade_a.py \
  --input-root ./output \
  --output-dir ./grade_a
```

此工具會掃描 `*.analysis.json`，只保留 `route_recommendation == "A"`，並把分析摘要與對應 `conv_<id>.md` 合併成單一檔案。

---

## 6. CLI 參數說明（`convert_and_analyze.py`）

### 6.1 必填 / 主要參數

- `--input`：輸入 JSON 路徑（必填）
- `--format`：`auto|chatgpt|claude`（預設 `auto`）
- `--output-root`：輸出目錄（預設 `.`）
- `--skip-analysis`：只轉檔不分析
- `--analysis-schema`：`default|salvage`（預設 `default`）

### 6.2 LLM 與認證

- `--provider`：`openai|anthropic`（預設 `openai`）
- `--model`：分析模型（除 `--skip-analysis` 與 `--dry-run` 外建議明確指定）
- `--api-key-env`：自訂第一階段 API key 環境變數名
- `--second-pass-provider`：第二階段 provider（salvage 用）
- `--second-pass-model`：第二階段模型（設了 second-pass-provider 時必填）
- `--second-pass-api-key-env`：自訂第二階段 API key 環境變數名

### 6.3 批次控制

- `--max-concurrency`：平行分析數（預設 `5`）
- `--retry`：失敗重試次數（預設 `3`）
- `--resume`：遇到既有 `.analysis.json` 就略過
- `--force`：搭配 `--resume` 時仍強制重跑
- `--sample N`：只處理前 N 筆（抽樣測試很實用）

### 6.4 salvage 語意控制

- `--language`：`auto|zh|en`（預設 `auto`；程式會映射為 marker 語系策略）
- `--marker-config`：marker 設定檔路徑（預設 `./marker_lexicon.yaml`）

### 6.5 觀測與估算

- `--dry-run`：只估算，不寫檔、不呼叫 API
- `--log-level`：`DEBUG|INFO|WARNING|ERROR`（預設 `INFO`）
- `--estimate-input-tokens`、`--estimate-output-tokens`
- `--estimate-second-pass-ratio`
- `--price-input-per-1m`、`--price-output-per-1m`

---

## 7. 分析 schema 與欄位

## 7.1 default schema

輸出需包含：

- `summary`（字串）
- `tags`（陣列，至少 1 個）
- `language`（字串）
- `quality_score`（0–100 數值）

## 7.2 salvage schema

輸出需包含：

- `topic`
- `valuable_residuals`（0–3 條）
- `drift_point`
- `next_steps`（0–2 條，若無行動可為 `暫不行動`）
- `route_recommendation`（`A|B|C|D`）
- `verdict`

並在流程中補充：

- `initial_route_recommendation`
- `final_route_recommendation`
- `calibration_applied`
- `calibration_confidence`
- `calibration_reason`

---

## 8. salvage 模式評分語意（實務重點）

- 此模式不是一般摘要，而是「殘值打撈」。
- 預設偏保守：不確定時往 `C/D`，避免高估。
- `A`：高價值、可長期保存的原則/模型/框架。
- `B`：即使不完整，但可直接進入專案紀錄、規格、任務、方法清單或決策紀錄。
- `C`：僅局部可摘錄，尚不足進入工作系統。
- `D`：整體不值得保存（資訊密度低、一般問答/翻譯/流水內容等）。

### 二階段流程

1. **First pass**：產生 salvage JSON 並套用硬規則正規化。  
2. **Second pass（選擇性）**：只在 `B/C` 邊界不清時做仲裁校準，避免誤判偏高。  

---

## 9. 輸出檔案

在 `--output-root` 下（預設當前目錄）：

- `conv_<safe_id>.md`
- `conv_<safe_id>.analysis.json`（啟用分析時）
- `index.csv`

`index.csv` 重點：

- 以 `id` upsert（重跑同一 id 會覆蓋，不重複追加）
- 包含 `route_recommendation`、`initial/final_route_recommendation`、`calibration_*`、`verdict` 等追蹤欄位
- 亦包含 `status`、`error` 便於批次巡檢

使用 `collect_grade_a.py` 後，在 `--output-dir` 另有：

- `conv_<safe_id>.md`（合併檔）
  - 前段：分析摘要表格 + 殘值 + next steps + 校準資訊
  - 後段：原始對話 Markdown

---

## 10. `marker_lexicon.yaml` 設定說明

- 檔名為 `.yaml`，但目前程式以 `json.loads(...)` 讀取，因此內容需是合法 JSON。
- 可定義 `common`、`zh`、`en` 區塊。
- 主要用於：
  - 強殘值 marker（如 framework / KPI / 門檻 / 原則）
  - verdict 正負語意 marker
  - no-action 步驟 marker

建議做法：

1. 先用預設詞彙跑一批資料。  
2. 觀察 `B/C/D` 分佈與誤判模式。  
3. 再逐步調整 marker，不要一次大改。

---

## 11. 錯誤處理與重試行為

- `401`：視為認證失敗，流程中止。
- `429`：依 `Retry-After` 或退避（`2**i`）重試。
- 網路/逾時錯誤：依 `--retry` 重試。
- LLM 回傳 JSON 解析失敗：該對話標記 `failed`。
- salvage 第二階段失敗：保留 first pass，`calibration_reason=second_pass_failed`。

---

## 12. 測試覆蓋重點

`tests/test_salvage_logic.py` 與 `tests/test_collect_grade_a.py` 已涵蓋：

- salvage 路由正規化（A/B/C/D）
- B blocker 語意降級
- second-pass 方向守門與 fallback
- CLI `--sample` / `--resume` / `--force` / `--dry-run`
- `index.csv` rerun 去重（upsert）
- A 級蒐集整合與缺檔容錯

---

## 13. 隱私與安全建議

輸出的 `.md` / `.analysis.json` / `index.csv` 可能含敏感資訊（對話內容、內部決策、個資片段）。建議：

- 固定輸出到獨立資料夾（例如 `./output`）
- 在 `.gitignore` 明確忽略輸出
- 提交前再次檢查是否誤納入機敏檔

---

## 14. 常見操作範本

### 小量驗證流程（先看格式）

```bash
python convert_and_analyze.py \
  --input ./export.json \
  --format auto \
  --skip-analysis \
  --sample 20 \
  --output-root ./output_sample
```

### salvage + 成本估算 + 正式跑

```bash
# 1) 估算
python convert_and_analyze.py \
  --input ./export.json \
  --format auto \
  --provider openai \
  --model gpt-4.1-mini \
  --analysis-schema salvage \
  --dry-run

# 2) 正式跑
python convert_and_analyze.py \
  --input ./export.json \
  --format auto \
  --provider openai \
  --model gpt-4.1-mini \
  --analysis-schema salvage \
  --output-root ./output \
  --max-concurrency 5 \
  --retry 3 \
  --resume

# 3) 蒐集 A 級
python collect_grade_a.py \
  --input-root ./output \
  --output-dir ./grade_a
```

---

如需擴充（例如新增 provider、加強輸出索引欄位、導入資料庫或向量索引），建議先從 `convert_and_analyze.py` 的 `normalize_*`、`analyze_conversation`、`IndexManager` 三個區塊著手。
