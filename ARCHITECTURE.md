# Architecture & Flow

This document explains how the Financial Report Agent works end to end, and
what each file is responsible for.

---

## 1. The big idea

A financial report has two halves that need very different tools:

| Half | Example | Best tool |
|------|---------|-----------|
| **Numbers** | revenue = 63,646 | a **structured data source** (deterministic, exact) |
| **Narrative** | "financially healthy, low leverage, strong cash" | an **LLM** (judgment, synthesis) |

The whole architecture follows one principle:

> **Let the data source own the numbers. Let the LLM own the prose. Let plain
> code own the orchestration and rendering.**

Numbers come from **yfinance** (deterministic, correct, no variance). The **LLM**
reads the deep-research report and writes the qualitative narrative. Neither is
asked to do the other's job — which is what makes the output reliable.

---

## 2. End-to-end flow

A company goes through four phases: **start → poll → build → render.**

```
                                   ┌─────────────── phase 1: START ───────────────┐
python agent.py "Vinamilk"  ──►  start_research()  ──►  deep-research interaction
                                        │                    (runs on Google, 5–11 min)
                                        ▼
                                  Job saved to jobs.json  (state = "running")


                                   ┌─────────────── phase 2: POLL ────────────────┐
python agent.py status  ──►  refresh_jobs()  ──►  check_research(id)
     (or the app's Refresh)          │                    │
                                     │            ("in_progress" → wait)
                                     │            ("completed"  → research_text)
                                     ▼
                                   phase 3


                                   ┌─────────────── phase 3: BUILD ───────────────┐
                              build_report(company, research_text):

                                resolve_ticker("Vinamilk") ─► "VNM.VN"     [LLM]
                                fetch_financials("VNM.VN")  ─► numbers      [yfinance]
                                        │
                              ┌─────────┴───────── numbers found? ──────────┐
                              │ YES (yfinance-primary)         │ NO (fallback)
                              ▼                                ▼
                    extract_narrative(text)          extract_financials(text)  [LLM]
                     ─► summary/verdict/health         ─► numbers from prose
                        highlights/risks/segments      + completeness gate
                              │                            (reextract_field)
                    data = narrative                       │
                    data.update(numbers) ◄─ yfinance wins  │
                              └───────────────┬────────────┘
                                              ▼
                                    has_usable_financials? ── no ──► job "failed"
                                              │ yes
                                              ▼
                                         write_report()  ─► reports/{co}.json + .md
                                         job state = "done"


                                   ┌────────────── phase 4: RENDER ───────────────┐
Streamlit app  ──►  render_report(json)  ──►  KPI tiles + verdict + charts
```

### Why it's asynchronous
The deep-research step takes minutes and runs on Google's servers. So the app
never blocks: `start_research` returns a **ticket** (interaction id) immediately,
and the app **polls** that ticket until it's done. This makes the CLI/app behave
like a **job queue** — start several companies, walk away, collect them later.
State lives in `jobs.json` so a job survives between runs.

### The completeness gate (fallback path only)
When yfinance has no data for a company, the LLM extracts numbers from prose —
which is unreliable. So there's a safety net:
1. `missing_critical_fields(data)` asks "is revenue missing?"
2. If so, `reextract_field` makes a second, targeted LLM pass anchored to the
   known years (so it can't invent phantom years).
3. If still missing, the report is written with a soft "data incomplete" note.

On the **yfinance-primary path this gate is unnecessary** — the data source
supplies the numbers directly.

---

## 3. What each file does

Dependencies flow one direction:
`schemas ← financials / research / data_source ← pipeline ← agent ← app`

### Core pipeline

**`schemas.py`** — the **data contracts.** Pydantic models describing the shape
of a report (`FinancialReport`, `NarrativeReport`, and the pieces:
`YearFinancial`, `Margins`, `Segment`, `BalanceSheet`, `CashFlow`). These are
what the LLM extraction is *enforced against* (the model literally cannot return
a malformed shape) and what the dashboard renders. One home so every module
agrees on the shape.

**`financials.py`** — **pure logic over the report dict.** No network, no LLM, no
I/O — just functions on plain dicts, so it's trivially testable:
- `has_usable_financials(data)` — does the report have any real number worth rendering?
- `missing_critical_fields(data)` — is revenue (latest year) missing?
- `merge_extraction(base, patch, add_years)` — fold a supplementary source into the
  report, filling **nulls only** (never overwriting). `add_years=True` lets a
  *trusted* source (yfinance) extend the year series; the default keeps an
  untrusted LLM pass from inventing phantom years.
- `_is_forecast_year` / `_drop_forecast_years` — strip forecast/plan years
  ("2026 Kế hoạch", "2026F") so the charts show actuals only.
- `_empty_report()` — the all-null baseline shape.

**`research.py`** — **the Google / LLM API boundary.** Only functions that call
Google:
- `start_research(company)` — kick off a background deep-research interaction; return its id.
- `check_research(id)` — poll an interaction; return `(status, research_text)`.
- `extract_narrative(text)` — one LLM call → the qualitative fields only (summary,
  verdict, health, highlights, risks, segments). Numbers come from elsewhere.
- `extract_financials(text)` — one LLM call → the *full* report (numbers + narrative);
  used only on the fallback path. Drops forecast years.
- `reextract_field(text, field, years)` — targeted second-pass revenue extraction,
  anchored to known years.

**`data_source.py`** — **structured financials from yfinance.**
- `resolve_ticker(name)` — the one small LLM call, `"Vinamilk" → "VNM.VN"`.
- `fetch_financials(ticker)` — yfinance → an **adapter** (`_adapt`) that maps the
  provider's fields to our schema in **pure code**: renames fields, normalizes raw
  currency to billions (÷1e9), and computes derived values (margins from
  revenue+profit, debt-to-equity, current ratio, free cash flow = operating +
  capex). Returns `{}` on any failure so callers degrade gracefully.

**`pipeline.py`** — **`build_report(company, research_text)`** — the report-building
brain. Routes between yfinance-primary and the LLM fallback (the diamond in the
flow above) and returns the finished report dict. Kept separate from the job
queue so it's testable and reusable on its own.

### Orchestration & I/O

**`agent.py`** — the **job queue + CLI.** Orchestration only:
- `start_research_jobs(companies)` — start research for each; save Jobs.
- `refresh_jobs()` — poll running jobs; for finished ones call `build_report`,
  then `write_report`. Each job is handled independently and saved as it finishes,
  so one job's failure (e.g. a rate limit) leaves it `running` to retry and never
  crashes the batch or rolls back another.
- `clear_finished_jobs()` — drop done/failed jobs from history.
- `__main__` — the `python agent.py <company>` / `status` CLI.

**`jobs.py`** — **persistence.** A `Job` dataclass (company, interaction id, state,
report path) and `JobStore`, a JSON-file-backed store with **atomic writes**
(temp file + `os.replace`) so a crash never corrupts `jobs.json`.

**`report.py`** — **the writer.** Turns a report dict into `reports/{slug}_{date}.md`
(human-readable) and a companion `.json` (which drives the dashboard).

**`app.py`** — the **Streamlit UI.** A start form, a Jobs tab (status of each
research run), and a Reports tab that reads a report's `.json` and calls
`render_report` to draw the KPI tiles, verdict banner, and charts.

**`charts.py`** — **ECharts builders.** Pure functions that turn report numbers
into chart `option` dicts (trend bars, segment donut, profit donut, cash-vs-debt,
cash-flow), plus the color palette and the render helper.

### Support

**`config.py`** — `REPORT_LANGUAGE` and all the **prompts** (`RESEARCH_PROMPT`,
`NARRATIVE_PROMPT`, `EXTRACT_PROMPT`, `REVENUE_PROMPT`).

**`model.py`** — the shared Gemini `client`, the `MODEL` (extraction/ticker) and
`RESEARCH_AGENT` names, loaded from env with defaults.

**`i18n.py`** — every user-facing string (report labels, chart labels, UI text,
job-event toasts) keyed by language. Change wording or add a language here only.

---

## 4. The report data shape

Everything downstream (writer, dashboard) consumes one dict:

```python
{
  "company": "Vinamilk", "date": "2026-08-06",
  "currency_unit": "tỷ VNĐ",
  "health": "good",                      # good | mixed | weak  → banner color
  "verdict": "…one-line assessment…",
  "summary": "…3–5 sentences…",
  "financials": [                        # per year, oldest first  → trend chart
     {"year": "2023", "revenue": 60368.9, "net_income": 8873.8}, …
  ],
  "margins": {"gross": 41.0, "operating": 16.8, "net": 14.8},
  "balance_sheet": {"cash": …, "debt": …, "debt_to_equity": …, "current_ratio": …},
  "cash_flow": {"operating": …, "free": …},
  "segments": [{"name": "…", "revenue": …}, …],   # donut (from research)
  "highlights": ["…", …],
  "risks": ["…", …],
  "research_text": "…full research report…"
}
```

- **Numbers** (`financials`, `margins`, `balance_sheet`, `cash_flow`, `currency_unit`)
  → from **yfinance** (or the LLM fallback).
- **Narrative** (`summary`, `verdict`, `health`, `highlights`, `risks`, `segments`)
  → from the **LLM** reading the deep research.

---

## 5. Key design decisions (and why)

- **yfinance-primary for numbers** — the LLM gathered revenue *non-deterministically*
  (rich one run, empty the next). A structured source is exact and consistent, so
  numbers no longer depend on LLM luck.
- **LLM only for narrative** — prose is where fuzziness is fine; numbers is where it
  isn't. Each tool does what it's good at.
- **Deterministic orchestration** — the "is the data sufficient?" decision is a plain
  `if` (`missing_critical_fields`), not an LLM "brain" — crisp questions get crisp code.
- **Schema-enforced extraction** — the LLM can't return a malformed shape, so the
  rest of the pipeline never defends against garbage structure.
- **Pipeline separated from the job queue** — `build_report` is a pure function of
  its inputs, so it's testable and reusable (e.g. for a future synchronous mode).
- **Resilient job loop** — one company's failure never sinks the batch; its job is
  left to retry.
