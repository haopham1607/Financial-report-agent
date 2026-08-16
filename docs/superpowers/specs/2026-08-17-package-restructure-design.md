# Package Restructure — Design

**Date:** 2026-08-17
**Status:** Approved, implementing

## Problem

All 14 modules sit flat in the project root, mixing entry points, the AI core,
tools, orchestration, and rendering with no signal about which is which. Four
concrete problems:

1. **Dead code.** `schemas.py` (68 lines) has zero importers since the agent loop
   replaced `write_narrative`; its `NarrativeReport`/`FinancialReport` models are
   no longer used by anything.
2. **A naming collision.** `agent.py` is the *job queue*, while `agent_loop.py` is
   the actual agent. The two most similarly-named files are the two least related.
3. **`app.py` does two jobs** (293 lines): the Streamlit page shell *and* the
   entire `render_report` dashboard.
4. **No boundaries.** Nothing in the layout says the AI core is separable from
   rendering, or that `data_source`/`web_search` are the agent's tools.

## Goal

Group the code by responsibility into one shallow package, delete the dead
module, and split `app.py` — **without changing behavior or the commands people
type.**

Explicit non-goal: deep multi-package ceremony (`core/`, `domain/`, `infra/`).
At ~1,650 lines that would cost more than it buys.

## Design

### Target structure

```
app.py                    ← entry shim: streamlit run app.py    (command unchanged)
agent.py                  ← entry shim: python agent.py "FPT"   (command unchanged)
finreport/
  __init__.py
  i18n.py                 ← i18n.py                (shared by every layer)
  agent/
    __init__.py
    loop.py               ← agent_loop.py          (the tool-calling agent)
    prompts.py            ← config.py              (REPORT_LANGUAGE, AGENT_PROMPT, EXCLUDE_DOMAINS)
    model.py              ← model.py               (Gemini client + MODEL)
  tools/
    __init__.py
    market_data.py        ← data_source.py         (yfinance + resolve_ticker)
    web_search.py         ← web_search.py          (Tavily)
  jobs/
    __init__.py
    queue.py              ← agent.py               (queue_jobs, refresh_jobs, clear_finished_jobs, _error_reason, store, CLI main)
    store.py              ← jobs.py                (Job, JobStore)
  reporting/
    __init__.py
    build.py              ← pipeline.py            (build_report)
    writer.py             ← report.py              (.md/.json writer, REPORTS_DIR)
    charts.py             ← charts.py              (ECharts builders)
    checks.py             ← financials.py          (has_usable_financials, missing_critical_fields)
  ui/
    __init__.py
    app.py                ← app.py's page shell    (form, tabs, deferred build, poll_jobs/show_jobs)
    render.py             ← app.py's render_report (the dashboard)
```

**Deleted:** `schemas.py` (dead code).

### Entry-point shims

The two documented commands must keep working unchanged, so the CLI body and the
Streamlit page body each become a `main()` the shim calls.

`agent.py` (root):
```python
"""Entry point: python agent.py "FPT" | python agent.py status"""

from finreport.jobs.queue import main

if __name__ == "__main__":
    main()
```

`app.py` (root):
```python
"""Entry point: streamlit run app.py"""

from finreport.ui.app import main

main()
```

`main()` is called unconditionally in `app.py` because Streamlit re-executes the
script on every interaction; the module body of `finreport/ui/app.py` holds only
definitions, and `main()` draws the page each rerun.

In `finreport/jobs/queue.py`, the existing `if __name__ == "__main__":` block
becomes `def main():` with the same body. In `finreport/ui/app.py`, the current
module-level page code (from the start form through the deferred-build block)
becomes the body of `def main():`.

Both shims sit in the project root, so `finreport/` is importable without any
`sys.path` manipulation.

### The `app.py` split

- `finreport/ui/render.py` — `render_report(data)` (currently `app.py:46-168`),
  plus its `L = get_labels()`. Imports `finreport.reporting.charts`.
- `finreport/ui/app.py` — everything else: `STATE_ICONS`/`STATE_TEXT`,
  `poll_jobs`, `show_jobs`, and `main()` (the start form, the Jobs and Reports
  tabs, and the deferred-build block). Imports `render_report` from
  `finreport.ui.render`.

### Tests

Tests stay a **flat `tests/` package** so `./.venv/bin/python -m tests` keeps
working exactly as today (its `__main__.py` discovers `test_*` modules via
`pkgutil`). Each file is renamed to match the module it now covers, and its
imports updated:

| Today | After | Covers |
|-------|-------|--------|
| `tests/test_agent_loop.py` | `tests/test_loop.py` | `finreport.agent.loop` |
| `tests/test_data_source.py` | `tests/test_market_data.py` | `finreport.tools.market_data` |
| `tests/test_web_search.py` | `tests/test_web_search.py` | `finreport.tools.web_search` |
| `tests/test_agent.py` | `tests/test_queue.py` | `finreport.jobs.queue` |
| `tests/test_pipeline.py` | `tests/test_build.py` | `finreport.reporting.build` |
| `tests/test_report.py` | `tests/test_writer.py` | `finreport.reporting.writer` |
| `tests/test_financials.py` | `tests/test_checks.py` | `finreport.reporting.checks` |

Test **bodies** are unchanged except for import lines and monkeypatch targets
(e.g. `agent.build_report` → `queue.build_report`, `agent_loop._model_turn` →
`loop._model_turn`). The suite passing unchanged is the proof the refactor is
behavior-preserving.

### Behavior preservation

This is a **pure restructure**. No logic changes, no renamed public functions, no
signature changes, no changed report shape, no prompt edits. The only content
changes are: file moves, the `schemas.py` deletion, wrapping two module bodies in
`main()`, and the `app.py` split.

Runtime paths that must keep resolving after the move:
- `finreport/jobs/store.py` — `JOBS_FILE = os.path.join(os.path.dirname(__file__), "jobs.json")`
  now resolves inside the package, so it must be re-anchored to the **project
  root** to keep using the existing top-level `jobs.json`.
- `finreport/reporting/writer.py` — `REPORTS_DIR` likewise must stay the
  top-level `reports/` directory.
- `finreport/tools/web_search.py` — `load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))`
  and the same call in `finreport/agent/model.py` must be re-anchored to the
  project root so the existing root `.env` is still found.

Each of these resolves through a single project-root constant, defined once in
`finreport/__init__.py` (one level above the package) and imported where needed
rather than recomputed in three files:

```python
# finreport/__init__.py
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

Consumers then use `os.path.join(ROOT, "jobs.json")`, `os.path.join(ROOT, "reports")`,
and `os.path.join(ROOT, ".env")`.

### Docs

`README.md` and `ARCHITECTURE.md` list modules by filename; both get their file
tables/sections updated to the new paths. The documented commands do not change.

## Testing

- `./.venv/bin/python -m tests` → `All test modules passed.` (same suite, same
  count, renamed files).
- `./.venv/bin/python -c "import finreport.jobs.queue, finreport.ui.app"` →
  imports cleanly (catches stale imports the tests might miss).
- `./.venv/bin/python agent.py status` → runs (the CLI shim works end to end).
- A grep for the old module names (`agent_loop`, `data_source`, `financials`,
  `pipeline`, `schemas`) across `*.py` returns nothing outside `finreport/`.

## Risks

- **Import churn.** Every internal import changes once. Mitigated by the test
  suite plus the explicit import check above.
- **Path anchoring.** The `.env`, `jobs.json`, and `reports/` lookups are the one
  place where moving files can silently change runtime behavior; the `ROOT`
  constant addresses this directly and the CLI smoke check proves it.
- **Streamlit shim.** Wrapping the page body in `main()` is the only structural
  change to the UI; a manual `streamlit run app.py` is the check.
