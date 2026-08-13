# Architecture & Flow

This document explains how the Financial Report Agent works end to end, and
what each file is responsible for.

---

## 1. The big idea

A financial report has parts that need very different tools:

| Part | Example | Best tool |
|------|---------|-----------|
| **Numbers** | revenue = 63,646 | a **structured data source** (deterministic, exact) |
| **Context** | "signed a USD 256M AI contract" | a **web search** (current, qualitative) |
| **The report** | "healthy — strong margins, low leverage…" | an **LLM writer** (synthesis) |

The architecture follows one principle:

> **The data source owns the numbers. A search gathers the context. A writer
> fuses them. Code owns the orchestration and rendering.**

Numbers come from **yfinance** (deterministic, consistent). A **web search**
(Tavily) gathers the qualitative context the numbers can't give, and a plain LLM
call **synthesizes** it into a fixed format. A **writer model** combines that with
the numbers — using the yfinance numbers as the source of truth, so the story
always matches the charts.

---

## 2. End-to-end flow

A company goes through three phases: **queue → build → render.**

```
                                   ┌─────────────── phase 1: QUEUE ───────────────┐
python agent.py "Vinamilk"  ──►  queue_jobs()  ──►  Job saved (running)
     (or the app's start form)                              in jobs.json   [instant]


                                   ┌─────────────── phase 2: BUILD ───────────────┐
python agent.py status  ──►  refresh_jobs()  ──►  for each pending job:
     (or the app's Refresh)                        build_report(company)

     build_report(company):
        resolve_ticker("Vinamilk")  → "VNM.VN"                 [tiny LLM call]
        fetch_financials("VNM.VN")  → NUMBERS                  [yfinance, pure code]
             revenue, net income, margins, balance sheet, cash flow
        gather_context("Vinamilk")  → CONTEXT + sources        [Tavily search + LLM synthesis]
             a fixed 8-section format (business, segments, developments,
             outlook, competitive position, growth drivers, risks, sources)
        write_narrative(numbers, context) → summary, verdict,  [LLM writer, schema]
             health, highlights, risks, segments
        data = narrative + NUMBERS + context + sources

        → has_usable_financials? — no → job "failed"
        → write_report()  → reports/{company}.json + .md
        → job "done"


                                   ┌────────────── phase 3: RENDER ───────────────┐
Streamlit app  ──►  render_report(json)  ──►  KPI tiles + verdict banner + charts
                                              + summary / highlights / risks
                                              + analysis text + sources
```

### Why a job queue (async)
The work is not instant (a web search + a synthesis + a writer call take seconds), and
the app is batch-oriented (several companies at once). So it stays a **job
queue**: `start` records jobs instantly; `refresh` builds the pending ones and
writes their reports. State lives in `jobs.json`, so jobs persist between runs
and a failure is retried. Each job is handled independently — one job's error
(e.g. a rate limit) leaves it `running` to retry without aborting the batch.

### Retrieval, synthesis, and the writer — separated steps
Context gathering is **decoupled from the LLM** and kept separate from the writer:
- `gather_context` — runs two **Tavily** web searches (`web_search.search`),
  dedupes the hits by URL, then a **plain** (no-tools) Gemini call synthesizes them
  into the fixed 8-section format → free text + cited sources.
- `write_narrative` — a **schema-enforced** call (no tools) that fuses that
  context with the authoritative numbers into guaranteed-valid structured output.

Decoupling retrieval (Tavily) from generation means context gathering uses
**Tavily's** quota — not the Gemini Search-grounding quota — and lets us steer and
exclude sources. The search freely gathers; the writer fuses with the numbers.

---

## 3. What each file does

Dependency flow (one direction):
`schemas ← financials / data_source / research ← pipeline ← agent ← app`
(and `research` uses the `web_search` tool)

### Core pipeline

**`schemas.py`** — the **data contracts.** Pydantic models describing a report
(`NarrativeReport`, and the pieces: `YearFinancial`, `Margins`, `Segment`,
`BalanceSheet`, `CashFlow`). The writer's output is *enforced* against
`NarrativeReport` (it cannot return a malformed shape) and the dashboard renders
this shape.

**`data_source.py`** — **structured financials from yfinance.**
- `resolve_ticker(name)` — one small LLM call, `"Vinamilk" → "VNM.VN"`.
- `fetch_financials(ticker)` — yfinance → an **adapter** (`_adapt`) that maps the
  provider's fields to our schema in **pure code**: renames fields, normalizes
  raw currency to billions (÷1e9), and computes derived values (margins,
  debt-to-equity, current ratio, free cash flow = operating + capex). Returns
  `{}` on any failure so callers degrade gracefully.

**`web_search.py`** — the **Tavily web-search tool**, isolated behind one
function: `search(query, max_results, exclude_domains)` → `[{title, uri, content}]`,
returning `[]` on a missing key or any error. Self-contained (loads `.env`, logs a
warning when the key is missing); swapping providers touches only this file.

**`research.py`** — **context gathering + the writer.**
- `gather_context(company)` — runs the two `SEARCH_QUERY_TEMPLATES` through
  `web_search.search` (passing `EXCLUDE_DOMAINS`), dedupes hits by URL, then a
  plain Gemini call synthesizes the fixed 8-section format (business, segments,
  developments, outlook, competitors, risks) → text + cited sources. Returns
  `("", [])` if the search yields nothing.
- `write_narrative(company, numbers, context)` — the **writer**: a plain,
  schema-enforced call that fuses the numbers (source of truth) with the context
  into the structured report fields (incl. `segments` + `segment_period`).

**`financials.py`** — **pure logic over the report dict** (no network/LLM/I/O):
- `has_usable_financials(data)` — does the report have any real number worth rendering?
- `missing_critical_fields(data)` — is revenue (latest year) missing? (drives the
  "data incomplete" note).

**`pipeline.py`** — **`build_report(company)`** — the report-building brain:
`resolve_ticker → fetch_financials → gather_context → write_narrative → combine`.
Returns the report dict (numbers + narrative + context + sources). Kept separate
from the job queue so it is testable and reusable.

### Orchestration & I/O

**`agent.py`** — the **job queue + CLI.** `queue_jobs` (queue),
`refresh_jobs` (build pending jobs → `build_report` → `write_report`, per-job
resilient + saved as each finishes), `clear_finished_jobs`, and the
`python agent.py …` CLI.

**`jobs.py`** — **persistence.** A `Job` dataclass and `JobStore`, a JSON-file
store with **atomic writes** (temp file + `os.replace`) so a crash never
corrupts `jobs.json`.

**`report.py`** — **the writer.** Turns a report dict into
`reports/{slug}_{date}.md` (human-readable, incl. sources) + a companion `.json`
(which drives the dashboard).

**`app.py`** — the **Streamlit UI.** A start form, a Jobs tab, and a Reports tab
that reads a report's `.json` and calls `render_report` to draw the KPI tiles,
verdict banner, charts, analysis, and sources.

**`charts.py`** — **ECharts builders.** Pure functions turning report numbers
into chart `option` dicts (trend, segment donut, profit donut, cash-vs-debt,
cash-flow), plus the palette and render helper.

### Support

**`config.py`** — `REPORT_LANGUAGE`; the two prompts `SEARCH_PROMPT` (the fixed
synthesis format; section headings follow `REPORT_LANGUAGE`) and `WRITER_PROMPT`
(fuse numbers + context → report); and the search config `SEARCH_QUERY_TEMPLATES`
(2 queries per company) + `EXCLUDE_DOMAINS`.

**`model.py`** — the shared Gemini `client` and the `MODEL` name (from env).

**`i18n.py`** — every user-facing string (report/chart/UI labels, job toasts)
keyed by language.

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
  "segments": [{"name": "…", "revenue": …}, …],   # donut (from the writer/context)
  "segment_period": "Cả năm 2025",       # period the segment figures cover → donut subtitle
  "highlights": ["…", …],
  "risks": ["…", …],
  "context": "…gathered context (the 8-section format)…",
  "sources": [{"title": "…", "uri": "…"}, …]
}
```

- **Numbers** (`financials`, `margins`, `balance_sheet`, `cash_flow`, `currency_unit`)
  → from **yfinance**.
- **Narrative** (`summary`, `verdict`, `health`, `highlights`, `risks`, `segments`,
  `segment_period`) → from the **writer**, using numbers + gathered context.
- **`context` / `sources`** → from the **Tavily search + synthesis** step.

---

## 5. Key design decisions (and why)

- **yfinance for numbers** — the LLM gathered figures non-deterministically; a
  structured source is exact and consistent, so numbers don't depend on LLM luck.
- **Retrieval decoupled from the LLM** — Tavily fetches web content and a plain
  Gemini call synthesizes it, so context gathering uses Tavily's quota (not the
  Gemini Search-grounding quota) and lets us steer/exclude sources.
- **Search gathers, the writer writes** — separated so retrieval + synthesis
  produce free-form context while the writer produces schema-enforced output.
- **Fixed synthesis format** — the synthesis returns the same standard-based
  sections every company, so the writer's input is predictable.
- **Writer grounded in the real numbers** — the report can't disagree with the charts.
- **Schema-enforced writer** — the writer cannot return a malformed shape.
- **Pipeline separated from the job queue** — `build_report` is a pure function
  of its input, so it's testable and reusable.
- **Resilient job loop** — one company's failure never sinks the batch.
