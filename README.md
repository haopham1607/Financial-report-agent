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
```

It is a genuine **tool-calling agent**: the model is given four tools and a goal,
and *it* decides what to call and when it has enough to finish.

```
company name
     │
     ▼
  ┌──────────────── the agent loop (agent_loop.py) ────────────────┐
  │  model picks a tool ──► code runs it ──► result fed back ──►   │
  │  repeat (max 8 steps) until the model calls submit_report      │
  │                                                                │
  │  tools:  resolve_ticker  ("Vinamilk" → "VNM.VN")               │
  │          fetch_financials (yfinance → the authoritative NUMBERS)│
  │          web_search       (Tavily → context + sources)         │
  │          submit_report    (the finished report; ends the loop) │
  └────────────────────────────────┬───────────────────────────────┘
                                   ▼
        code stamps the yfinance NUMBERS in last (authoritative)
                                   │
                                   ▼
                report .json / .md ─► Streamlit dashboard
```

**The core design principle:** the agent is free to decide *how* to research, but
**the numbers are not up to it.** Every figure comes from the `fetch_financials`
tool (yfinance) and is stamped into the report by code **after** the agent
finishes — so the model can search, re-search, and self-correct, yet the story
always matches the charts.

| Stage | Owner | Owns |
|-------|-------|------|
| Numbers | **yfinance** (via the `fetch_financials` tool, stamped by code) | every figure → the charts |
| Research | **the agent** (`web_search` → Tavily) | which queries to run, when to search again |
| Report | **the agent** (`submit_report`) | verdict, summary, segments, highlights, risks |

Retrieval uses **Tavily** rather than Gemini's Search grounding, so it draws on
Tavily's own quota and lets us steer/exclude sources.

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
| `.env` | `GEMINI_API_KEY` | *(required)* — the model that drives the agent loop |
| `.env` | `TAVILY_API_KEY` | *(context)* — the `web_search` tool; without it, reports are numbers-only |
| `.env` | `RISK_AGENT_MODEL` | `gemini-3.6-flash` (the agent's model) |
| `config.py` | `AGENT_PROMPT` | the agent's goal + how to use its tools |
| `config.py` | `EXCLUDE_DOMAINS` | domains barred from `web_search` |
| `agent_loop.py` | `MAX_STEPS` | `8` — how many turns the agent gets before it must finish |

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
./.venv/bin/python -m tests.test_agent_loop    # the agent loop (tools, steps, assembly)
```

## Project layout

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full flow and per-file logic. In
short:

| File | Role |
|------|------|
| `app.py` | Streamlit UI |
| `agent.py` | job queue + CLI (orchestration) |
| `pipeline.py` | `build_report()` — thin wrapper over the agent loop |
| `agent_loop.py` | **the agent**: tool schemas, the loop, and report assembly |
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
