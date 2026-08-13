# Financial Report Agent

Generate a visual **financial-health dashboard** for any public company from a
plain name. You type `Vinamilk` (or `Apple`, or a comma-separated list); the app
pulls its financials, gathers current context from the web, and renders a report
with charts, a health verdict, highlights, risks, and cited sources.

Output is written in **Vietnamese** by default (configurable) — but the
companies can be from **any market** (Vietnam via `.VN` tickers, US, etc.).

---

## What it does

For each company it produces a report with:

- **KPI tiles** — latest revenue, net income (with YoY growth), net margin
- **A health verdict** — a color-coded `good` / `mixed` / `weak` banner + plain-language summary
- **Charts** — revenue & profit trend, revenue by segment, profit share, cash vs debt, cash flow
- **A financial-safety section** — debt-to-equity, current ratio
- **Highlights & risks** — short qualitative bullets
- The gathered analysis text and its **sources**

## How it works

```
company name
     │
     ▼
 resolve_ticker (LLM) ─► ticker ─► yfinance ─► NUMBERS  (revenue, margins,
                                    (deterministic)      balance sheet, cash flow)
     │                                              │
     ▼                                              │
 gather_context ─► Tavily web search ─► plain-LLM synthesis ─► CONTEXT + sources
     │  (business, segments, developments, outlook, competitors, risks)
     └───────────────────────────────┬──────────────┘
                                      ▼
                     write_narrative (LLM writer)
                       fuses NUMBERS + CONTEXT ─► structured report
                                      │
                                      ▼
                     report .json / .md ─► Streamlit dashboard
```

**The core design principle:** the **numbers come from a structured data source
(yfinance) — deterministic and authoritative.** A **web search** (Tavily) gathers
the qualitative context the numbers can't provide, a plain LLM call **synthesizes**
it into a fixed format, and a **writer model** fuses that with the numbers. So the
story always matches the charts. Three roles:

| Stage | Tool | Owns |
|-------|------|------|
| Numbers | **yfinance** | every figure → the charts |
| Context | **Tavily web search** + plain-LLM synthesis | business, segments, developments, risks + sources |
| Report | **writer model** | fuses numbers + context → verdict, summary, highlights, risks |

Context retrieval is deliberately **decoupled** from the LLM (Tavily fetches, a
plain Gemini call synthesizes) — it uses Tavily's own quota instead of the
Gemini Search-grounding quota, and lets us steer/exclude sources.

## Setup

```bash
cd Financial_report_agent
python -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then edit .env: add GEMINI_API_KEY and TAVILY_API_KEY
```

`requirements.txt`: `google-genai`, `python-dotenv`, `streamlit`, `yfinance`,
`tavily-python`.

Get a free Gemini key at [aistudio.google.com](https://aistudio.google.com) and
a free Tavily key at [tavily.com](https://tavily.com). Without a Tavily key the
app still runs, but reports build from the **numbers only** (no context/sources).

## Usage

### Web app (recommended)
```bash
./.venv/bin/streamlit run app.py
```
Enter one or more company names, start them, and hit **Refresh** to build the
reports (the work runs on refresh; a batch takes a little while).

### Command line
```bash
python agent.py "FPT"                 # queue one job, exit immediately
python agent.py "FPT, Apple, MWG"     # queue several at once
python agent.py status                # build pending jobs; write their reports
```

Reports land in `reports/` as a `.json` (drives the dashboard) plus a `.md`
(human-readable). The web app reads them from there.

## Configuration

| Where | Setting | Default |
|-------|---------|---------|
| `config.py` | `REPORT_LANGUAGE` | `"Vietnamese"` (set `"English"` to switch all output) |
| `.env` | `GEMINI_API_KEY` | *(required)* — name→ticker, context synthesis, writer |
| `.env` | `TAVILY_API_KEY` | *(context)* — web search; without it, reports are numbers-only |
| `.env` | `RISK_AGENT_MODEL` | `gemini-3.6-flash` (name→ticker + synthesis + writer) |
| `config.py` | `SEARCH_QUERY_TEMPLATES` / `EXCLUDE_DOMAINS` | the 2 Tavily queries per company; domains barred from search |

## Tests

Plain-assert test files (no framework needed), living in the `tests/` package.
Run from the project root with `-m` so they can import the app's modules:

```bash
./.venv/bin/python -m tests                    # the whole suite
./.venv/bin/python -m tests.test_financials    # pure report-dict logic
./.venv/bin/python -m tests.test_data_source   # yfinance adapter
./.venv/bin/python -m tests.test_pipeline      # build_report: numbers + context → report
./.venv/bin/python -m tests.test_agent         # job-loop resilience
./.venv/bin/python -m tests.test_report        # markdown report (incl. segment period)
./.venv/bin/python -m tests.test_web_search    # Tavily search wrapper
./.venv/bin/python -m tests.test_research      # gather_context (search + synthesis)
```

## Project layout

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full flow and per-file logic. In
short:

| File | Role |
|------|------|
| `app.py` | Streamlit UI |
| `agent.py` | job queue + CLI (orchestration) |
| `pipeline.py` | `build_report()` — assembles a report from the sources |
| `research.py` | `gather_context` (Tavily search → LLM synthesis) + `write_narrative` (writer) |
| `web_search.py` | Tavily web-search tool (isolated; `[]` on missing key / error) |
| `data_source.py` | yfinance structured financials + name→ticker |
| `financials.py` | pure report-dict logic (completeness gate) |
| `schemas.py` | the structured report data contracts |
| `report.py` | writes the `.md` + `.json` |
| `charts.py` | ECharts chart builders |
| `jobs.py` | job persistence (`JobStore`) |
| `i18n.py` | all user-facing text, per language |
| `config.py` | language + prompts |
| `model.py` | Gemini client + model name |
