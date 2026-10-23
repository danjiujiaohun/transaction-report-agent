# Stock Market Company Analysis Report Agent

A listed-company research report generation service built on **FastAPI + LangGraph**. It accepts a company name or ticker, plans the research points, collects A-share / US-stock structured data plus web search results, and produces a **framework-driven, fully English** Markdown analysis report. The project ships a built-in web frontend — open it in a browser to enter a stock and view the report — and also exposes a REST API for integration.

## 1. Problem Statement

Producing professional, evidence-based equity research is slow and inconsistent. A competent analyst needs days to classify the asset, verify the financials, run a bull/bear debate, establish a falsifiable valuation range, and write an auditable memo. In practice most people — and most generic AI financial tools — fall back to rephrasing search results into a wall of text with no valuation discipline, no falsifiability, and no traceable data.

This project addresses that gap by encoding an **institutional research workflow into reusable skills** and a deterministic pipeline:

- **No asset classification → wrong yardstick.** Loss-making growth names get "PE is cheap" verdicts, and mature asset-heavy leaders get ignored. The agent routes each company into the right framework (value / growth / platform) and applies the matching valuation tool.
- **No opposing view → confirmation bias.** The agent forces a structured long/short debate before any conclusion, instead of a single-sided "cheap because PE is low" claim.
- **No falsifiability → one-shot opinions.** Reports ship with falsification signal tables and year-by-year assumption tables so a thesis can be tracked and invalidated, not just read once.
- **No audit trail → unverifiable numbers.** Revenue must come as segment hard tables, GAAP vs Non-GAAP separated, with raw data persisted and gaps explicitly flagged.

## 2. Key Features Implemented

- **Three-stage pipeline** — `plan → search → report`, orchestrated by LangGraph.
- **A-share structured data** — real-time quotes, financial statements, valuation history, research reports, consensus EPS, holder count, dividends, fund flows, dragon-tiger board.
- **US-stock structured data** — quote/valuation snapshot (incl. analyst target price), annual-report key lines, 1-year price history via yfinance (Yahoo / SEC sources).
- **Framework-driven research skills** — value / growth / platform frameworks (19 skills loaded) with institutional rules: investment debate, implied value bands, falsification signals, attribution.
- **Research dimension keywords** — a checkbox UI lets users pick focus areas (Business model, Moat, TAM, SOTP, …); an **Auto-match** step has the model light up the most relevant keywords for a given company before generation, which the user can still adjust.
- **Forced English output** — reports are post-scanned for Chinese characters; any leak triggers an automatic English rewrite.
- **Web search** — portable Tavily API (AutoGLM WebSearch as fallback).
- **Pluggable LLM** — any OpenAI-compatible endpoint (DeepSeek / Qwen / OpenAI) or local Ollama.
- **Built-in web frontend** — a dark, terminal-style page served by the backend itself (no separate build step).
- **REST API + CORS** — submit / poll task status; frontend and external clients share the same endpoints.

## 3. Technical Design & Architecture

The service is a single FastAPI process. The analysis runs as a **LangGraph StateGraph** with three nodes, executed in a background thread and surfaced to clients via an **async task + polling** pattern.

```
                 ┌───────────────────────────────────────────────┐
  HTTP request   │  FastAPI (app/main.py)                        │
  /api/analyze ──▶  submit_task() ──▶ background thread          │
                 │      │                                        │
                 │      ▼                                        │
                 │  LangGraph pipeline (app/agent/)              │
                 │   plan_queries → do_search → write_report     │
                 │      │            │              │            │
                 │      │            │              ▼            │
                 │      │            │        skill prompt +     │
                 │      │            │        forced-EN rewrite  │
                 │      ▼            ▼                           │
                 │  LLM (OpenAI/Ollama)   tools/a_stock, us_stock│
                 └───────────────────────────────────────────────┘
                        ▲                     ▲
                        │                     │
               /api/analyze/{id}     /api/dimensions, /api/recommend-dimensions
```

**Pipeline nodes** ([app/agent/nodes.py](app/agent/nodes.py)):

- `plan_queries` — asks the LLM to generate 3–5 search keywords, optionally steered by the user-selected research dimensions.
- `do_search` — resolves the input to an A-share code or US ticker, pulls structured data, then runs web search and aggregates everything into `search_results`.
- `write_report` — injects the base system prompt plus the tailored skills prompt, generates the Markdown report, and runs the Chinese-character guard.

**Key components**:

| Component | Path | Responsibility |
|---|---|---|
| App entry & routes | [app/main.py](app/main.py) | FastAPI routes, static mount, CORS |
| Config | [app/config.py](app/config.py) | `.env`-backed settings (pydantic `BaseSettings`) |
| LLM factory | [app/llm.py](app/llm.py) | OpenAI-compatible / Ollama instantiation |
| Agent graph | [app/agent/graph.py](app/agent/graph.py) | Compiles the `plan → search → report` StateGraph |
| Agent state | [app/agent/state.py](app/agent/state.py) | TypedDict carried across nodes |
| Async tasks | [app/agent/tasks.py](app/agent/tasks.py) | In-memory task store + background threads |
| Skills loader | [app/skills/loader.py](app/skills/loader.py) | Scans `skills/*/SKILL.md`, builds prompt overview |
| Dimension mapping | [app/skills/dimensions.py](app/skills/dimensions.py) | Keyword → framework skill mapping + LLM recommendation |
| A-share tools | [app/tools/a_stock/](app/tools/a_stock/) | Tencent/Sina/EastMoney/baostock collectors |
| US-stock tools | [app/tools/us_stock/](app/tools/us_stock/) | yfinance collectors, ticker normalization, throttling, proxy |
| Web search | [app/tools/web_search.py](app/tools/web_search.py) | Tavily / AutoGLM adapters |
| Frontend | [static/index.html](static/index.html) | Self-contained dark UI + Markdown renderer |

**Task model**: `POST /api/analyze` returns a `task_id` immediately (`202 Accepted`); the client polls `GET /api/analyze/{task_id}` until `status == "done"`. Tasks live in process memory, so a restart clears them — for multi-instance deployment, replace [app/agent/tasks.py](app/agent/tasks.py) with a Redis/DB backend.

**Skill execution**: each framework skill is a Markdown rulebook (`skills/*/SKILL.md`). By default only the skills overview (name + description) is injected into the report prompt. When a user selects dimension keywords, the matched framework skill's **full rules** are injected so the selected framework actually drives the report, and the same dimensions steer the search-query planning.

## Directory Structure

```
transaction-report-agent/
├── app/
│   ├── main.py               # FastAPI entry & routes
│   ├── config.py             # Settings (.env)
│   ├── llm.py                # LLM factory (OpenAI-compatible / Ollama)
│   ├── agent/                # LangGraph: state / nodes / graph / tasks
│   ├── models/schemas.py     # Request/response models
│   ├── skills/               # loader.py + dimensions.py
│   └── tools/
│       ├── web_search.py     # Web search (Tavily / AutoGLM)
│       ├── a_stock/          # A-share collectors
│       └── us_stock/         # US-stock collectors (yfinance)
├── skills/                   # Report generation rules (Markdown, see credits below)
├── static/                   # Web frontend (dark UI, calls the REST API)
├── requirements.txt
├── .env.example
└── README.md
```

## Requirements

- Python 3.10+ (verified on 3.13)
- Network access to the A-share data sources (Tencent / Sina / EastMoney / baostock are domestic endpoints; overseas networks may be restricted)

## Configuration

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Edit `.env` and fill in the settings:

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | yes | `openai` (recommended) or `ollama` |
| `OPENAI_BASE_URL` | when provider=openai | OpenAI-compatible base URL, e.g. `https://api.deepseek.com` |
| `OPENAI_API_KEY` | when provider=openai | Your API key |
| `OPENAI_MODEL` | when provider=openai | Model name, e.g. `deepseek-chat` |
| `OLLAMA_BASE_URL` | when provider=ollama | Local Ollama URL, default `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | when provider=ollama | Local model name, default `qwen3.5:9b` |
| `TAVILY_API_KEY` | recommended | Tavily web-search key (portable, primary) |
| `WEBSEARCH_TOKEN_URL` | no | AutoGLM search token service (fallback when no Tavily key) |
| `SKILLS_DIR` | no | Skills directory, default `skills` |
| `HOST` / `PORT` | no | Bind address/port, default `0.0.0.0:8000` |
| `US_STOCK_PROXY` | no | HTTP proxy for US-stock requests (e.g. `http://127.0.0.1:7890`); only US-stock traffic goes through it. Leave empty for direct connection |

> **Web search (pick one)**: with `TAVILY_API_KEY` set, Tavily is used (recommended — one key is all you need on a new environment). With no key and a local `53699` token service available, AutoGLM is used; otherwise search degrades to "structured data + search unavailable".

## Installation & Run

```bash
# 1. Clone and enter the project
git clone <your-repo-url> transaction-report-agent
cd transaction-report-agent

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables (see previous section)
cp .env.example .env   # then edit .env with your LLM & search keys

# 5. Start the service (either way works)
# Option A: call the venv uvicorn directly, no activation needed
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# Option B: activate then start (activation only affects the current shell)
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> The service listens on `0.0.0.0:8000`. On the same machine or LAN you can open it directly in a browser; on a cloud host, allow port `8000` in the security group / firewall.

After startup you can access:

- **Web frontend**: `http://<host>:8000/` (enter a name/ticker to generate a report)
- **Health check**: `http://localhost:8000/api/health`
- **Swagger docs**: `http://localhost:8000/docs`

### Web Frontend

The frontend is served by the same backend process from the `static/` directory — no separate build or Node service is required:

1. Open `http://<host>:8000/`.
2. Enter a company name or ticker: US stocks such as `AAPL`, `MSFT`, `TSLA` (the TRY shortcuts are the US market-cap Top 10), A-shares such as `600519`.
3. Optional: click **Auto-match** to let the model light up the most relevant research dimensions, then adjust the checkboxes as needed.
4. Click **Generate Report** (or press Enter) — the page shows the four-step progress (plan → gather → write → done).
5. When finished, the report renders automatically: left TOC navigation, Markdown formatting (tables / code blocks), copy raw Markdown, export PDF.

All page data comes from the backend `/api/*` endpoints, so a single backend process serves both the UI and the API.

### API Usage

Analysis uses an **async task** model: submission returns a `task_id` immediately, and the client polls until `done` (a full run typically takes 1–3 minutes).

**1. Submit an analysis** (returns immediately, `202 Accepted`):

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"company": "AAPL", "dimensions": ["Moat", "PE/PB", "FCF"]}'
```

- `company` — company name or ticker.
- `dimensions` (optional) — selected research-dimension keywords; when present, the matched framework skill's full rules are injected and the search is steered accordingly.

Response:

```json
{
  "task_id": "c3c561e018ba",
  "company": "AAPL",
  "status": "running",
  "phase": "Gathering data & web search",
  "report": null,
  "error": null
}
```

**2. Poll task status**:

```bash
curl http://localhost:8000/api/analyze/c3c561e018ba
```

Status fields:

- `status`: `pending` → `running` → `done` / `failed`
- `phase`: current stage label
- `report`: the Markdown report, present only when `status=done`
- `error`: error message, present only when `status=failed`

**3. List research dimensions**:

```bash
curl http://localhost:8000/api/dimensions
```

Returns the four dimension groups (Universal / Value leader / Growth·tech / Platform·upside) with their keywords and the framework skill each group maps to.

**4. Recommend dimensions for a company**:

```bash
curl -X POST http://localhost:8000/api/recommend-dimensions \
  -H "Content-Type: application/json" \
  -d '{"company": "AAPL"}'
```

Returns `{"keywords": ["Moat", "PE/PB", ...]}` — the model's suggested focus areas, used by the frontend Auto-match step.

> Tasks are stored in process memory and cleared on restart; for multi-instance deployment, replace [app/agent/tasks.py](app/agent/tasks.py) with a Redis/DB implementation.

Health-check response (includes search availability):

```json
{
  "status": "ok",
  "llm_provider": "openai",
  "llm_model": "deepseek-chat",
  "skills_loaded": 19,
  "search_available": true
}
```

## Report Generation Rules (skills)

The `skills/` directory holds the report-generation rules as Markdown (including data sources, field definitions, and rate-limiting conventions). They are injected into the LLM prompt on each run to constrain structure, data caliber, and the "never fabricate data" baseline.

> **Credits**: the report-generation skills originate from <https://github.com/zengfancy/invest-skill>. Thanks to its author.

## Research Dimensions

The frontend exposes a "Research focus" selector with four groups of keywords, each mapping to a research framework:

| Group | Keywords | Framework skill |
|---|---|---|
| Universal | Business model · Competition · Narrative · Catalysts · Debate · Tracking · Value band | (applies to any framework) |
| Value leader | FCF · Moat · Margins · Share · PE/PB · Risks | `value-leader-research` |
| Growth / tech | Growth path · TAM · Product · Dilution · Runway · Valuation route · PEG/PS | `growth-tech-research` |
| Platform / upside | Segments · Cash cow · Disruption · SOTP · Option · Capex | `platform-leader-research` |

Workflow: **Auto-match** has the model pick the most relevant keywords for the entered company and light them up; the user can then adjust the selection before generating. Selecting a framework keyword injects that skill's full rules into the report and steers the search queries.

## Report Highlights

From a capital-management standpoint, the value of this report is not "more information" but that it turns an **institutional investment decision process** into a reproducible output: classify the asset, counter the biases, set the risk boundary, and leave a trackable investment thesis — each step answering a question a PM must resolve before sizing a position.

**The deliverable.** A single run produces three layers with consistent module naming across the three frameworks:

```text
output/{ticker}-{date}/
├── 00-Overview.md                     # index + one-line verdict + key charts + per-chapter summaries
├── 01-Investment Summary.md … 09/11/12-*.md  # thick sub-reports (9 for value / 11 for growth / 12 for platform)
├── {symbol}-research-report.md        # standalone research report (chart-first)
└── data/                              # raw fetches + crawl logs (auditable)
```

Each highlight below is tagged with the module it lands in, so it can be verified directly in the corresponding sub-report.

### 1. Classify the asset first — the framework decides the valuation discipline

- Three frameworks auto-route: **steady value leaders** ask "what cash flow am I buying" (how the moat monetizes into ROE/FCF, whether capital returns are durable); **growth tech** ask "is the growth verifiable" (orders, design-ins, pipeline, paid retention — not sector narrative); **platform / brand / IP giants** ask "what narrative is the market trading" (segment-level SOTP).
- The valuation tool follows the asset class: heavy assets use **PB-ROE**, profitable growth uses **Forward PE/PEG**, unprofitable uses **PS + earnings-path back-solve**, platforms use **SOTP** — mechanically preventing "PE is cheap" being applied to a loss-maker, the single most common value-trap source in retail and sell-side write-ups.

> **Module**: framework choice + one-line verdict → `00-Overview` meta area; valuation routing → `06/08/09-Current Valuation`.

### 2. Hear the bear before sizing — an IC debate written into the report (Investment Debate)

- Every report closes the valuation chapter with a debate card: **≥3 cheap arguments + ≥3 expensive/discount arguments + a neutral baseline**, each bound to a premise (vs history / vs growth / vs "this company without that risk").
- It ports the investment committee's long/short confrontation into the memo: before a position is formed, the opposing case is forced out, countering confirmation bias.

> **Module**: debate card → `06/08/09-Current Valuation`; the verdict rolls up into `01-Investment Summary` and the standalone research report.

### 3. Risk embedded — value bands give ranges, falsification signals give exits

- **Implied value bands** provide a build/add **range basis** rather than a price target, and flag "if the consensus denominator is too optimistic, a low forward PE may be fake-cheap".
- Every report ships a **falsification signal table** (`signal | strengthens | weakens`) — the exit conditions written on day one, the pre-mortem discipline most retail investors lack.
- The base-case revenue/net-income path becomes an annual assumption table, reconcilable quarter by quarter: the report turns from a one-shot opinion into a **verifiable investment thesis**.

> **Module**: value bands → the scenario section of the valuation sub-report; falsification table + annual reconciliation → `09/11/12-Synthesis & Tracking Checklist`.

### 4. Expectation gap is the alpha — consensus and pricing viewed separately

- Market-view evolution is its own chapter: sell-side rating / consensus changes are shown **separately from actual pricing**, with the narrative split into 2–4 phases.
- The **expectation gap** (this framework's forecast vs consensus — high/low/close, and where) is written out explicitly; excess return usually comes from where consensus is wrong, so it is treated as an object of analysis rather than a by-product.

> **Module**: `07/09/10-Market View Evolution`.

### 5. Position-review-grade attribution — volatility explained down to nameable events

- Attribution is forced into layers: mid-term (1–6 months) answers how the pricing framework shifted; near-term (5–10 sessions) must land on a **nameable event (date + actor + content)**, banning "sentiment / sector weakness" hand-waving.
- For a holder, this directly serves the "add or cut" decision: separate a fundamental event from noise before acting.

> **Module**: `08/10/11-Recent Price Move Attribution`, cross-referencing `03-Major Changes in 1–2 Years`.

### 6. Due-diligence-grade evidence chain — numbers traceable, compliance defensible

- Revenue must come as **segment hard tables** (annual-report caliber), GAAP vs Non-GAAP separated; unavailable data is explicitly marked "not obtained" with the gap stated, never silently skipped.
- Raw fetches are persisted under `data/` (with crawl logs and timestamps), so every number in a conclusion is traceable.
- Financials may be cached, but **catalyst search is never skipped**: attribution requires a fresh 7–14 day news refresh.

> **Module**: segment tables + GAAP/Non-GAAP split → `02-Fundamentals` (value) / `02-Business Model & Financial Profile` (growth) / `02-Segments` + `04-Mature Business` (platform); data gaps → `00-Overview` data notes; raw trail → `data/`.

### 7. A week of analyst drafting, done overnight

- Three delivery layers map to three institutional scenarios: **thick sub-reports** (deep diligence), **overview** (a 5-minute IC brief), **standalone research report** (external/archive), plus a raw data directory — each non-redundant.
- Forced English output is a hard constraint (post-scan for Chinese characters with an automatic rewrite, see [nodes.py](app/agent/nodes.py)), so reports drop straight into English-language workflows.

> **Module**: `00-Overview.md` (brief layer) + `01~09/11/12` sub-reports (diligence layer) + `{symbol}-research-report.md` (finished layer) + `data/` (workpaper layer).

### Vs. generic AI financial reports (capital-management view)

| Decision step | Generic AI report gives you | This project gives you | Where to verify |
|---|---|---|---|
| Asset classification | One template for everything | value/growth/platform routing, yardstick matched to asset | `00-Overview` + valuation sub-report |
| Position basis | "Valuation looks low" | long/short debate + bound premises + 3-tier value band | valuation sub-report debate card |
| Risk management | A boilerplate risk paragraph | falsification table = exit conditions written day one | Synthesis & Tracking Checklist |
| Alpha source | Restates consensus | explicit expectation gap: consensus vs pricing | Market View Evolution |
| Position tracking | Read once, discard | annual assumption reconciliation + per-period signal checks | Synthesis & Tracking Checklist |
| Compliance workpaper | Untraceable sources | segment hard tables + raw data persisted | Fundamentals sub-report + `data/` |

## US-Stock Data Sources

US-stock structured collection is implemented in [app/tools/us_stock/](app/tools/us_stock/), corresponding to the `skills/us-stock-*` rules. Sources and their addresses:

### 1. Yahoo Finance (primary, wired in code)

Fetched via the [yfinance](https://github.com/ranaroussi/yfinance) library, covering quote snapshot, annual three statements, analyst targets, and historical candles:

| Data | Underlying endpoint | Notes |
|---|---|---|
| Historical candles / close | `https://query1.finance.yahoo.com/v8/finance/chart/{ticker}` | ~1 year of daily candles for returns & drawdown |
| Quote & valuation snapshot | `https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}` | price, market cap, PE/PB, forward PE, 52-week range |
| Annual three statements | same (`income-statement` / `balance-sheet` / `cash-flow-statement` modules) | GAAP key lines (revenue / gross / net / EPS, etc.) |
| Analyst expectations | same (`upgrade-downgrade-history` / `earnings-trend` modules) | mean/median target, ratings, coverage count |

- Page entry: <https://finance.yahoo.com/quote/AAPL> (replace `AAPL` with any ticker)
- Rate limiting: serial calls, ≥0.4s spacing + random jitter (see [helpers.py](app/tools/us_stock/helpers.py))
- Network: Yahoo returns 403/rate-limits on some egress IPs; configure `US_STOCK_PROXY` to route through a proxy

### 2. SEC EDGAR (filings & disclosures, documented in skills)

| Purpose | Address |
|---|---|
| ticker → CIK mapping | `https://www.sec.gov/files/company_tickers.json` |
| Filing list (10-K / 10-Q / 8-K / Form 4) | `https://data.sec.gov/submissions/CIK{cik}.json` |
| Raw filing files | `https://www.sec.gov/Archives/edgar/data/{cik}/` |

Requires a recognizable `User-Agent` (customizable via `SEC_USER_AGENT`), otherwise 403s are likely.

### 3. FRED macro data (optional)

- API: `https://api.stlouisfed.org/fred/series/observations` (Fed rates, CPI, employment, etc.)
- API key: <https://fred.stlouisfed.org/docs/api/api_key.html> (env var `FRED_API_KEY`)

### 4. Finnhub (optional enhancement)

- Company news: `https://finnhub.io/api/v1/company-news`
- Rating changes: `https://finnhub.io/api/v1/stock/recommendation`
- API key: <https://finnhub.io/register> (env var `FINNHUB_API_KEY`)

### 5. Polygon (optional quote fallback)

- <https://polygon.io> (env var `POLYGON_API_KEY`)

> **Wiring status**: the pipeline currently calls item 1 programmatically (yfinance: quote / financials / history) plus Tavily web search as fallback (`https://api.tavily.com/search`). Items 2–5 are documented extension paths in the skills, enabled on demand. All sources follow the "never fabricate data; mark unavailable data as not obtained" discipline.

## FAQ

- **`/` returns 404**: ensure the `static/` directory exists at the project root (built-in frontend); if upgrading from an older version, restart the service to reload the static mount.
- **Empty search results / `search_available: false`**: check whether `TAVILY_API_KEY` is set and whether `https://api.tavily.com` is reachable.
- **A-share data unavailable**: usually an overseas/office network that cannot reach domestic endpoints directly; `fund flows` (EastMoney push2his) applies connection-level risk control on some IPs and degrades gracefully to "fetch failed" rather than erroring.
- **US-stock structured data unavailable (quote/financials/history show fetch failure)**: usually Yahoo returning 403/rate-limit on the current egress IP; set `US_STOCK_PROXY` and retry. When the proxy is unavailable the report still generates, degrading to web-search-only with the data gap flagged in the report.
- **Local 502 (with a proxy enabled)**: the project automatically adds `127.0.0.1`/`localhost` to `NO_PROXY` so local services like Ollama are not intercepted by the system proxy.
