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

     build_report(company) → run_agent(company):        [the agent loop]

        repeat up to MAX_STEPS (8):
            ask the model what to do next (it sees the 4 tools)
            run the tool(s) it chose, feed the result back:
               resolve_ticker(name)   → "VNM.VN"        [tiny LLM call]
               fetch_financials(tk)   → NUMBERS         [yfinance, pure code]
               web_search(query)      → results + sources  [Tavily]
               submit_report(...)     → ends the loop
        (the model decides the order, how many searches, and when to stop;
         it can re-resolve/re-search if something looks wrong)

        data = the agent's narrative + context + sources
        data.update(NUMBERS)   ← code stamps the yfinance figures LAST

        → has_usable_financials? — no → job "failed"
        → write_report()  → reports/{company}.json + .md
        → job "done"  (+ "incomplete" note if revenue or the narrative is missing)


                                   ┌────────────── phase 3: RENDER ───────────────┐
Streamlit app  ──►  render_report(json)  ──►  KPI tiles + verdict banner + charts
                                              + summary / highlights / risks
                                              + analysis text + sources
```

### Why a job queue (async)
The work is not instant (the agent loop takes several model calls + searches), and
the app is batch-oriented (several companies at once). So it stays a **job
queue**: `start` records jobs instantly; `refresh` builds the pending ones and
writes their reports. State lives in `jobs.json`, so jobs persist between runs
and a failure is retried. Each job is handled independently — one job's error
(e.g. a rate limit) leaves it `running` to retry without aborting the batch.

### Agent, not workflow — and the guardrails that keep it reliable
The build is a **tool-calling agent loop**, not a fixed sequence: the model is
given the four tools and the goal (`AGENT_PROMPT`) and decides what to call, how
many times to search, and when it has enough. That buys autonomy — it can notice
an ambiguous name and re-resolve, or search again when the context is thin — at
the cost of determinism. Four guardrails keep it dependable:

- **Numbers are stamped by code, last.** `_assemble` never takes a figure from the
  model; `report.update(numbers)` writes the yfinance values over anything the
  agent said, so a hallucinated number cannot reach the charts.
- **`MAX_STEPS = 8`** bounds the loop, so it can never run away.
- **Output is coerced.** The model's `submit_report` args are defensively
  normalised (missing/garbage fields → sane defaults), so bad output degrades
  instead of crashing the report writer.
- **The completeness gate.** If the agent hits its step limit without submitting,
  the report has numbers but no narrative — `missing_critical_fields` flags
  `"narrative"` and the job reports "incomplete" rather than silent success.

Retrieval uses **Tavily** (`web_search.search`), not Gemini Search grounding, so
it draws on Tavily's own quota and lets us steer and exclude sources.

---

## 3. What each file does

Dependency flow (one direction):
`i18n / agent (prompts, model, loop) ← tools ← reporting ← jobs ← ui`
(entry shims `app.py` / `agent.py` sit at the root and call into the package)

### Core pipeline

**`finreport/tools/market_data.py`** — **structured financials from yfinance.**
- `resolve_ticker(name)` — one small LLM call, `"Vinamilk" → "VNM.VN"`.
- `fetch_financials(ticker)` — yfinance → an **adapter** (`_adapt`) that maps the
  provider's fields to our schema in **pure code**: renames fields, normalizes
  raw currency to billions (÷1e9), and computes derived values (margins,
  debt-to-equity, current ratio, free cash flow = operating + capex). Returns
  `{}` on any failure so callers degrade gracefully.

**`finreport/tools/web_search.py`** — the **Tavily web-search tool**, isolated behind one
function: `search(query, max_results, exclude_domains)` → `[{title, uri, content}]`,
returning `[]` on a missing key or any error. Self-contained (loads `.env`, logs a
warning when the key is missing); swapping providers touches only this file.

**`finreport/agent/loop.py`** — **the agent.** Three parts:
- **The tool schemas** — Gemini `FunctionDeclaration`s for `resolve_ticker`,
  `fetch_financials`, `web_search`, and `submit_report` (the terminal tool). This
  is the menu the model chooses from.
- **`run_agent(company)`** — the loop: `_model_turn` asks the model what to do,
  `_dispatch` runs the chosen tool (returning `{"error": ...}` instead of raising),
  the result is appended as a function-response turn so the model sees it, and it
  repeats up to `MAX_STEPS`. Along the way it keeps the latest non-empty
  `fetch_financials` result and accumulates `web_search` sources (deduped by URL).
- **`_assemble(final, numbers, sources)`** — builds the report dict: the agent's
  narrative (defensively coerced), then `context`/`sources`, then
  `report.update(numbers)` **last** so the yfinance figures are authoritative.

**`finreport/reporting/checks.py`** — **pure logic over the report dict** (no network/LLM/I/O):
- `has_usable_financials(data)` — does the report have any real number worth rendering?
- `missing_critical_fields(data)` — is revenue (latest year) missing, or the
  narrative blank (the agent never submitted)? Drives the "data incomplete" note.

**`finreport/reporting/build.py`** — **`build_report(company)`** — a thin wrapper that runs
`agent_loop.run_agent(company)`. Kept separate from the job queue so the queue
depends on a stable `build_report(company) -> dict` contract.

### Orchestration & I/O

**`finreport/jobs/queue.py`** — the **job queue + CLI.** `queue_jobs` (queue),
`refresh_jobs` (build pending jobs → `build_report` → `write_report`, per-job
resilient + saved as each finishes), `clear_finished_jobs`, and the
`python agent.py …` CLI.

**`finreport/jobs/store.py`** — **persistence.** A `Job` dataclass and `JobStore`, a JSON-file
store with **atomic writes** (temp file + `os.replace`) so a crash never
corrupts `jobs.json`.

**`finreport/reporting/writer.py`** — **the writer.** Turns a report dict into
`reports/{slug}_{date}.md` (human-readable, incl. sources) + a companion `.json`
(which drives the dashboard).

**`finreport/ui/app.py`** — the **Streamlit UI.** A start form, a Jobs tab, and a Reports tab
that reads a report's `.json` and calls `render_report` to draw the KPI tiles,
verdict banner, charts, analysis, and sources.

**`finreport/reporting/charts.py`** — **ECharts builders.** Pure functions turning report numbers
into chart `option` dicts (trend, segment donut, profit donut, cash-vs-debt,
cash-flow), plus the palette and render helper.

### Support

**`finreport/agent/prompts.py`** — `REPORT_LANGUAGE`; `AGENT_PROMPT` (the agent's goal, how to use
its tools, and the report fields it must submit — written in `REPORT_LANGUAGE`);
and `EXCLUDE_DOMAINS` (domains barred from `web_search`).

**`finreport/agent/model.py`** — the shared Gemini `client` and the `MODEL` name (from env).

**`finreport/i18n.py`** — every user-facing string (report/chart/UI labels, job toasts)
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
  `segment_period`) → from the **agent's `submit_report` call** (coerced).
- **`context` / `sources`** → the agent's `analysis` text, and the deduped
  sources accumulated from its **`web_search`** calls.

---

## 5. Key design decisions (and why)

- **yfinance for numbers** — the LLM gathered figures non-deterministically; a
  structured source is exact and consistent, so numbers don't depend on LLM luck.
- **An agent, not a fixed pipeline** — the model chooses its own tools and when to
  stop, so it can re-resolve an ambiguous name or search again when context is
  thin, instead of following one hardcoded path.
- **Autonomy, but not over the numbers** — code stamps the yfinance figures in
  last, so the report can't disagree with the charts no matter what the agent says.
- **Bounded and coerced** — `MAX_STEPS` caps the loop and the agent's output is
  normalised, so nondeterminism can't hang the build or crash the report writer.
- **Retrieval via Tavily** — a dedicated search tool (not Gemini Search grounding)
  uses Tavily's quota and lets us steer/exclude sources.
- **Agent separated from the job queue** — `build_report` keeps a stable contract,
  so the loop is testable and swappable behind it.
- **Resilient job loop** — one company's failure never sinks the batch.
