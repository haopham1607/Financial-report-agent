# Financial Report Agent

Generate a visual **financial-health dashboard** for any public company from a
plain name. You type `Vinamilk` (or `Apple`, or a comma-separated list); the app
researches the company, pulls its financials, and renders a report with charts,
a health verdict, highlights, and risks.

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
- The full underlying research text

## How it works (in one picture)

```
company name
     │
     ▼
 deep research agent ──► research text (prose: narrative, context, segments)
     │                          │
     │                          ▼
     │                   extract_narrative ──► summary, verdict, health,
     │                    (LLM)                 highlights, risks, segments
     ▼
 resolve_ticker (LLM) ─► ticker ─► yfinance ─► revenue, margins, balance
                                    (numbers)   sheet, cash flow  (deterministic)
                                       │
                                       ▼
                          build_report() merges them
                                       │
                                       ▼
                     report .json / .md ──► Streamlit dashboard
```

**The core design principle:** the **numbers come from a structured data source
(yfinance) — deterministic and authoritative** — while the **LLM only writes the
narrative** (what the numbers mean). Numbers are facts; prose is judgment. If a
company isn't on yfinance, it falls back to extracting numbers from the research
text with the LLM.

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
Enter one or more company names, start the research, and hit **Refresh** to
collect finished reports (research runs in the background, ~5–11 min each).

### Command line
```bash
python agent.py "FPT"                 # start one research job, exit immediately
python agent.py "FPT, Apple, MWG"     # start several at once
python agent.py status                # poll jobs; write reports for finished ones
```

Reports land in `reports/` as a `.json` (drives the dashboard) plus a `.md`
(human-readable). The web app reads them from there.

## Configuration

| Where | Setting | Default |
|-------|---------|---------|
| `config.py` | `REPORT_LANGUAGE` | `"Vietnamese"` (set `"English"` to switch all output) |
| `.env` | `GEMINI_API_KEY` | *(required)* |
| `.env` | `RISK_AGENT_MODEL` | `gemini-3.6-flash` (extraction + name→ticker) |
| `.env` | `RISK_AGENT_RESEARCH_AGENT` | `deep-research-preview-04-2026` |

## Tests

Plain-assert test files, no framework needed:

```bash
./.venv/bin/python test_financials.py     # pure report-dict logic
./.venv/bin/python test_data_source.py    # yfinance adapter
./.venv/bin/python test_pipeline.py       # source routing in build_report
./.venv/bin/python test_agent.py          # job-loop resilience
```

## Project layout

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full flow and per-file logic. In
short:

| File | Role |
|------|------|
| `app.py` | Streamlit UI |
| `agent.py` | job queue + CLI (orchestration) |
| `pipeline.py` | `build_report()` — assembles a report from the sources |
| `research.py` | the Google deep-research + LLM extraction calls |
| `data_source.py` | yfinance structured financials + name→ticker |
| `financials.py` | pure report-dict logic (merge, completeness, forecast filter) |
| `schemas.py` | the structured report data contracts |
| `report.py` | writes the `.md` + `.json` |
| `charts.py` | ECharts chart builders |
| `jobs.py` | job persistence (`JobStore`) |
| `i18n.py` | all user-facing text, per language |
| `config.py` | language + prompts |
| `model.py` | Gemini client + model names |
