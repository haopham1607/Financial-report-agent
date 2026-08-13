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
 gather_context (grounded web search) ─► qualitative CONTEXT + sources
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
(yfinance) — deterministic and authoritative.** A **grounded web search** gathers
the qualitative context the numbers can't provide, and a **writer model** fuses
the two into the report. So the story always matches the charts. Three roles:

| Stage | Tool | Owns |
|-------|------|------|
| Numbers | **yfinance** | every figure → the charts |
| Context | **grounded search** (Google Search tool) | business, segments, developments, risks + sources |
| Report | **writer model** | fuses numbers + context → verdict, summary, highlights, risks |

## Setup

```bash
cd Financial_report_agent
python -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then edit .env and add your GEMINI_API_KEY
```

`requirements.txt`: `google-genai`, `python-dotenv`, `streamlit`, `yfinance`.

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
| `.env` | `GEMINI_API_KEY` | *(required)* |
| `.env` | `RISK_AGENT_MODEL` | `gemini-3.6-flash` (search + writer + name→ticker) |

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
| `research.py` | the model calls: `gather_context` (grounded search) + `write_narrative` (writer) |
| `data_source.py` | yfinance structured financials + name→ticker |
| `financials.py` | pure report-dict logic (completeness gate) |
| `schemas.py` | the structured report data contracts |
| `report.py` | writes the `.md` + `.json` |
| `charts.py` | ECharts chart builders |
| `jobs.py` | job persistence (`JobStore`) |
| `i18n.py` | all user-facing text, per language |
| `config.py` | language + prompts |
| `model.py` | Gemini client + model name |
