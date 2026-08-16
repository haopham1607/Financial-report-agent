# Package Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the 14 flat root modules into a `finreport/` package grouped by responsibility, delete dead `schemas.py`, and split `app.py` — without changing behavior or the commands people type.

**Architecture:** Three bottom-up tasks, each ending with the full test suite green. Task 1 moves the foundation (i18n, agent core, tools); Task 2 moves jobs + reporting and turns root `agent.py` into a shim; Task 3 moves the UI, splits `render_report` out, and updates the docs. Root `app.py` and `agent.py` survive as 3-line entry shims so the documented commands are unchanged.

**Tech Stack:** Python 3, `git mv` for history-preserving moves, the project's plain-assert test files.

## Global Constraints

- **This is a pure restructure.** No logic changes, no renamed public functions, no signature changes, no prompt edits, no report-shape changes. Only: file moves, the `schemas.py` deletion, wrapping two module bodies in `main()`, and the `app.py` split.
- **The documented commands must not change:** `./.venv/bin/streamlit run app.py` and `./.venv/bin/python agent.py "FPT"` / `agent.py status`.
- **Use `git mv`** for every move so history is preserved.
- **Tests stay a flat `tests/` package** so `./.venv/bin/python -m tests` keeps working; only filenames and import lines change.
- **The suite passing unchanged is the proof.** After every task: `./.venv/bin/python -m tests` must print `All test modules passed.`
- **Runtime paths resolve through `ROOT`** (defined in `finreport/__init__.py`), never `os.path.dirname(__file__)`, for `.env`, `jobs.json`, and `reports/`.
- **Use the venv:** `./.venv/bin/python`, never bare `python`.
- **Every commit message ends with:** `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Work from the project root: `Financial_report_agent/`.

---

### Task 1: Package scaffold + move the foundation (i18n, agent core, tools)

**Files:**
- Create: `finreport/__init__.py`, `finreport/agent/__init__.py`, `finreport/tools/__init__.py`
- Move: `i18n.py` → `finreport/i18n.py`; `config.py` → `finreport/agent/prompts.py`; `model.py` → `finreport/agent/model.py`; `agent_loop.py` → `finreport/agent/loop.py`; `data_source.py` → `finreport/tools/market_data.py`; `web_search.py` → `finreport/tools/web_search.py`
- Delete: `schemas.py`
- Modify (import lines only): `pipeline.py`, `report.py`, `agent.py`, `app.py`
- Rename tests: `tests/test_agent_loop.py` → `tests/test_loop.py`; `tests/test_data_source.py` → `tests/test_market_data.py`

**Interfaces:**
- Produces: `finreport.ROOT` (str, absolute project-root path); `finreport.i18n.get_labels()`; `finreport.agent.prompts.{REPORT_LANGUAGE, AGENT_PROMPT, EXCLUDE_DOMAINS}`; `finreport.agent.model.{MODEL, client}`; `finreport.agent.loop.{run_agent, MAX_STEPS, _model_turn, _dispatch, _assemble}`; `finreport.tools.market_data.{resolve_ticker, fetch_financials, _adapt}`; `finreport.tools.web_search.{search, _client}`. All function names and signatures are unchanged from their old modules.

- [ ] **Step 1: Create the package scaffold**

Create `finreport/__init__.py`:

```python
"""Financial Report Agent — an LLM agent that builds company health reports.

ROOT is the project root (the directory holding app.py / agent.py / .env). Every
runtime path — .env, jobs.json, reports/ — resolves through it, so moving a module
inside the package never changes where those files live.
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

Create `finreport/agent/__init__.py`:

```python
"""The agent: its prompt, its model client, and the tool-calling loop."""
```

Create `finreport/tools/__init__.py`:

```python
"""The tools the agent can call: market data and web search."""
```

- [ ] **Step 2: Move the modules and delete the dead one**

Run:
```bash
mkdir -p finreport/agent finreport/tools
git mv i18n.py finreport/i18n.py
git mv config.py finreport/agent/prompts.py
git mv model.py finreport/agent/model.py
git mv agent_loop.py finreport/agent/loop.py
git mv data_source.py finreport/tools/market_data.py
git mv web_search.py finreport/tools/web_search.py
git rm schemas.py
git mv tests/test_agent_loop.py tests/test_loop.py
git mv tests/test_data_source.py tests/test_market_data.py
```
Expected: all moves succeed; `schemas.py` removed.

- [ ] **Step 3: Update imports inside the moved modules**

In `finreport/i18n.py`, change:
```python
from config import REPORT_LANGUAGE
```
to:
```python
from finreport.agent.prompts import REPORT_LANGUAGE
```

In `finreport/agent/loop.py`, change the import block:
```python
from config import AGENT_PROMPT, EXCLUDE_DOMAINS
from data_source import fetch_financials, resolve_ticker
from model import MODEL, client
from web_search import search
```
to:
```python
from finreport.agent.model import MODEL, client
from finreport.agent.prompts import AGENT_PROMPT, EXCLUDE_DOMAINS
from finreport.tools.market_data import fetch_financials, resolve_ticker
from finreport.tools.web_search import search
```

In `finreport/tools/market_data.py`, change:
```python
from model import MODEL, client
```
to:
```python
from finreport.agent.model import MODEL, client
```

- [ ] **Step 4: Re-anchor the two `.env` lookups to ROOT**

In `finreport/agent/model.py`, replace the `load_dotenv(...)` line with:
```python
from finreport import ROOT

load_dotenv(os.path.join(ROOT, ".env"))
```
(place the `from finreport import ROOT` with the other imports at the top).

In `finreport/tools/web_search.py`, replace the `load_dotenv(...)` line with:
```python
from finreport import ROOT

load_dotenv(os.path.join(ROOT, ".env"))
```
(same placement).

Both files already `import os`; keep that import.

- [ ] **Step 5: Update the root modules that import the moved ones**

In `pipeline.py`, change `from agent_loop import run_agent` to:
```python
from finreport.agent.loop import run_agent
```

In `report.py`, change `from i18n import get_labels` to:
```python
from finreport.i18n import get_labels
```

In `agent.py`, change `from i18n import get_labels` to:
```python
from finreport.i18n import get_labels
```

In `app.py`, change `from i18n import get_labels` to:
```python
from finreport.i18n import get_labels
```

(Leave every other import in those four files alone — they move in Task 2/3.)

- [ ] **Step 6: Update the moved tests' imports**

In `tests/test_loop.py`, change `import agent_loop` to:
```python
from finreport.agent import loop as agent_loop
```

In `tests/test_market_data.py`, change `from data_source import _adapt` to:
```python
from finreport.tools.market_data import _adapt
```

In `tests/test_web_search.py`, change `import web_search` to:
```python
from finreport.tools import web_search
```

Using `as agent_loop` / `import web_search` keeps every existing `agent_loop.X` and `web_search.X` reference in the test bodies working unchanged — the bodies must not otherwise be edited.

- [ ] **Step 7: Run the full suite**

Run: `./.venv/bin/python -m tests`
Expected: `All test modules passed.`

If a module fails to import, the cause is a missed import line from Steps 3–6 — fix that line, do not change any logic.

- [ ] **Step 8: Verify no stale references remain**

Run:
```bash
grep -rnE "^(import|from) (agent_loop|data_source|web_search|config|model|i18n|schemas)\b" --include=*.py .
```
Expected: no output. (`from finreport...` imports do not match this pattern.)

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: move i18n, agent core and tools into the finreport package

Adds finreport/ with ROOT (project-root anchor for .env/jobs.json/reports),
finreport/agent/ (prompts, model, loop) and finreport/tools/ (market_data,
web_search). Deletes dead schemas.py. Pure move — no logic changes.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Move jobs + reporting; root `agent.py` becomes a shim

**Files:**
- Create: `finreport/jobs/__init__.py`, `finreport/reporting/__init__.py`, new root `agent.py` (shim)
- Move: `jobs.py` → `finreport/jobs/store.py`; `agent.py` → `finreport/jobs/queue.py`; `pipeline.py` → `finreport/reporting/build.py`; `report.py` → `finreport/reporting/writer.py`; `charts.py` → `finreport/reporting/charts.py`; `financials.py` → `finreport/reporting/checks.py`
- Modify (import lines only): `app.py`
- Rename tests: `tests/test_agent.py` → `tests/test_queue.py`; `tests/test_pipeline.py` → `tests/test_build.py`; `tests/test_report.py` → `tests/test_writer.py`; `tests/test_financials.py` → `tests/test_checks.py`

**Interfaces:**
- Consumes: `finreport.ROOT`, `finreport.i18n.get_labels`, `finreport.agent.loop.run_agent` (Task 1).
- Produces: `finreport.jobs.store.{Job, JobStore, JOBS_FILE}`; `finreport.jobs.queue.{queue_jobs, refresh_jobs, clear_finished_jobs, store, main}`; `finreport.reporting.build.build_report`; `finreport.reporting.writer.{write_report, REPORTS_DIR}`; `finreport.reporting.charts` (all builders + palette, unchanged); `finreport.reporting.checks.{has_usable_financials, missing_critical_fields}`. `main()` is new (the extracted CLI body); everything else keeps its existing name and signature.

- [ ] **Step 1: Create the package scaffold**

Create `finreport/jobs/__init__.py`:

```python
"""The job queue: what work is pending, and running it."""
```

Create `finreport/reporting/__init__.py`:

```python
"""Turning a built report into files and charts, and gating what is usable."""
```

- [ ] **Step 2: Move the modules**

Run:
```bash
mkdir -p finreport/jobs finreport/reporting
git mv jobs.py finreport/jobs/store.py
git mv agent.py finreport/jobs/queue.py
git mv pipeline.py finreport/reporting/build.py
git mv report.py finreport/reporting/writer.py
git mv charts.py finreport/reporting/charts.py
git mv financials.py finreport/reporting/checks.py
git mv tests/test_agent.py tests/test_queue.py
git mv tests/test_pipeline.py tests/test_build.py
git mv tests/test_report.py tests/test_writer.py
git mv tests/test_financials.py tests/test_checks.py
```
Expected: all moves succeed.

- [ ] **Step 3: Re-anchor `jobs.json` and `reports/` to ROOT**

In `finreport/jobs/store.py`, replace the `JOBS_FILE = ...` line with:
```python
from finreport import ROOT

JOBS_FILE = os.path.join(ROOT, "jobs.json")
```
(place the `from finreport import ROOT` with the other imports at the top; keep `import os`).

In `finreport/reporting/writer.py`, replace the `REPORTS_DIR = ...` line with:
```python
from finreport import ROOT

REPORTS_DIR = os.path.join(ROOT, "reports")
```
(same placement; keep `import os`).

- [ ] **Step 4: Update imports inside the moved modules**

In `finreport/jobs/queue.py`, change the import block:
```python
from financials import has_usable_financials, missing_critical_fields
from finreport.i18n import get_labels
from jobs import Job, JobStore
from pipeline import build_report
from report import write_report
```
to:
```python
from finreport.i18n import get_labels
from finreport.jobs.store import Job, JobStore
from finreport.reporting.build import build_report
from finreport.reporting.checks import (has_usable_financials,
                                        missing_critical_fields)
from finreport.reporting.writer import write_report
```

In `finreport/reporting/build.py`, the import is already `from finreport.agent.loop import run_agent` (Task 1) — leave it.

In `finreport/reporting/writer.py`, the import is already `from finreport.i18n import get_labels` (Task 1) — leave it.

- [ ] **Step 5: Extract the CLI into `main()`**

In `finreport/jobs/queue.py`, replace the trailing line:
```python
if __name__ == "__main__":
```
with:
```python
def main():
    """The `python agent.py ...` CLI: queue companies, or build pending jobs."""
```
Keep the entire existing body below it exactly as-is (it is already indented one level, which is now the function body). The body uses `sys.exit(...)`; that still works inside a function.

- [ ] **Step 6: Create the root `agent.py` shim**

Create `agent.py` at the project root:

```python
"""Entry point for the CLI — keeps `python agent.py "FPT"` working.

    python agent.py FPT              queue a job, exit immediately
    python agent.py FPT, Apple       queue several at once
    python agent.py status           build pending jobs; write their reports

The implementation lives in finreport/jobs/queue.py.
"""

from finreport.jobs.queue import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Update `app.py`'s imports**

In `app.py`, change:
```python
import charts
from agent import clear_finished_jobs, refresh_jobs, queue_jobs, store
from report import REPORTS_DIR
```
to:
```python
from finreport.jobs.queue import (clear_finished_jobs, queue_jobs,
                                  refresh_jobs, store)
from finreport.reporting import charts
from finreport.reporting.writer import REPORTS_DIR
```
(`from finreport.i18n import get_labels` is already correct from Task 1.)

- [ ] **Step 8: Update the moved tests' imports**

In `tests/test_queue.py`, change:
```python
import agent
from jobs import Job
```
to:
```python
from finreport.jobs import queue as agent
from finreport.jobs.store import Job
```
The alias `as agent` keeps every `agent.store` / `agent.build_report` / `agent.refresh_jobs` monkeypatch and reference in the body working unchanged.

Also in `tests/test_queue.py`, `test_transient_errors_get_friendly_messages` has an
import **inside the function body** — change that line from
`    from i18n import get_labels` to:
```python
    from finreport.i18n import get_labels
```
(keep it inside the function, at its current indentation).

In `tests/test_build.py`, change `import pipeline` to:
```python
from finreport.reporting import build as pipeline
```

In `tests/test_writer.py`, change:
```python
import report
from i18n import get_labels
```
to:
```python
from finreport.i18n import get_labels
from finreport.reporting import writer as report
```

In `tests/test_checks.py`, change:
```python
from financials import has_usable_financials, missing_critical_fields
```
to:
```python
from finreport.reporting.checks import (has_usable_financials,
                                        missing_critical_fields)
```

Test bodies must not otherwise be edited.

- [ ] **Step 9: Run the suite and the CLI smoke check**

Run: `./.venv/bin/python -m tests`
Expected: `All test modules passed.`

Run: `./.venv/bin/python agent.py status`
Expected: it prints the job list (or `No jobs yet...`) without a traceback — this proves the shim, the extracted `main()`, and the ROOT-anchored `jobs.json` all work. It may also build a pending job; that is fine.

Run:
```bash
./.venv/bin/python -c "from finreport.jobs.store import JOBS_FILE; from finreport.reporting.writer import REPORTS_DIR; print(JOBS_FILE); print(REPORTS_DIR)"
```
Expected: both paths point at the **project root** (`.../Financial_report_agent/jobs.json` and `.../Financial_report_agent/reports`), NOT inside `finreport/`.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: move jobs and reporting into the package; agent.py is a shim

finreport/jobs/ (queue, store) and finreport/reporting/ (build, writer, charts,
checks). The CLI body becomes queue.main(), called by a thin root agent.py so
'python agent.py ...' is unchanged. jobs.json and reports/ now resolve via ROOT.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Move the UI, split `render_report` out, update the docs

**Files:**
- Create: `finreport/ui/__init__.py`, `finreport/ui/render.py`, new root `app.py` (shim)
- Move: `app.py` → `finreport/ui/app.py`
- Modify: `README.md`, `ARCHITECTURE.md`

**Interfaces:**
- Consumes: `finreport.jobs.queue.{clear_finished_jobs, queue_jobs, refresh_jobs, store}`, `finreport.reporting.charts`, `finreport.reporting.writer.REPORTS_DIR`, `finreport.i18n.get_labels` (Tasks 1–2).
- Produces: `finreport.ui.render.render_report(data: dict) -> None`; `finreport.ui.app.main() -> None`.

- [ ] **Step 1: Create the scaffold and move `app.py`**

Run:
```bash
mkdir -p finreport/ui
git mv app.py finreport/ui/app.py
```

Create `finreport/ui/__init__.py`:

```python
"""The Streamlit frontend: the page shell and the report dashboard."""
```

- [ ] **Step 2: Extract `render_report` into `finreport/ui/render.py`**

Create `finreport/ui/render.py` with this header, then **move the entire existing `render_report` function** (currently in `finreport/ui/app.py`, from `def render_report(data: dict) -> None:` through the end of its body — the last line is the `st.markdown(...)` inside the `sources` expander) into it, unchanged:

```python
"""The report dashboard: turns one report dict into the visual page.

Split from app.py (the page shell) so each file has one job.
"""

import streamlit as st

from finreport.i18n import get_labels
from finreport.reporting import charts

L = get_labels()


# <-- the existing render_report function goes here, body unchanged -->
```

- [ ] **Step 3: Wrap the page body of `finreport/ui/app.py` in `main()`**

In `finreport/ui/app.py`:

1. Delete the now-moved `render_report` function.
2. Replace the import block at the top with:

```python
"""Streamlit page shell: the start form, the Jobs tab and the Reports tab.

The dashboard itself lives in finreport/ui/render.py. Run via the root app.py:
    streamlit run app.py
"""

import glob
import json
import os

import streamlit as st

from finreport.i18n import get_labels
from finreport.jobs.queue import (clear_finished_jobs, queue_jobs,
                                  refresh_jobs, store)
from finreport.reporting.writer import REPORTS_DIR
from finreport.ui.render import render_report
```

3. Keep `L = get_labels()`, `STATE_ICONS`, `STATE_TEXT`, `poll_jobs()` and `show_jobs()` at module level, unchanged.
4. Wrap everything from the `# --- Start form ---` comment through the end of the file (the deferred-build block) in a function:

```python
def main() -> None:
    """Draw the page. Streamlit re-runs this on every interaction."""
```

Indent that whole block one level to become the function body. Do not reorder or edit any of it — `st.set_page_config`, `st.title` and `st.caption` (currently near the top of the file, above the helpers) stay where they are at module level.

- [ ] **Step 4: Create the root `app.py` shim**

Create `app.py` at the project root:

```python
"""Entry point for the web app — keeps `streamlit run app.py` working.

The implementation lives in finreport/ui/.
"""

from finreport.ui.app import main

main()
```

`main()` is called unconditionally: Streamlit re-executes this script on every
interaction, and the module body of `finreport/ui/app.py` holds only definitions.

- [ ] **Step 5: Verify the app imports and the suite passes**

Run:
```bash
./.venv/bin/python -c "import finreport.ui.app, finreport.ui.render, finreport.jobs.queue; print('imports OK')"
```
Expected: `imports OK` (this catches a stale import in the UI, which the test suite does not cover).

Run: `./.venv/bin/python -m tests`
Expected: `All test modules passed.`

- [ ] **Step 6: Verify no stale root-module references remain anywhere**

Run:
```bash
grep -rnE "^(import|from) (agent_loop|data_source|web_search|config|model|i18n|schemas|jobs|pipeline|report|charts|financials)\b" --include=*.py .
```
Expected: no output.

- [ ] **Step 7: Update the docs**

In `README.md`, replace the file table under "Project layout" with:

```markdown
| File | Role |
|------|------|
| `app.py` / `agent.py` | entry points (shims into the package) |
| `finreport/agent/loop.py` | **the agent**: tool schemas, the loop, report assembly |
| `finreport/agent/prompts.py` | language, `AGENT_PROMPT`, `EXCLUDE_DOMAINS` |
| `finreport/agent/model.py` | Gemini client + model name |
| `finreport/tools/market_data.py` | yfinance financials + name→ticker |
| `finreport/tools/web_search.py` | Tavily web-search tool |
| `finreport/jobs/queue.py` | job queue + CLI (`queue_jobs`, `refresh_jobs`) |
| `finreport/jobs/store.py` | job persistence (`Job`, `JobStore`) |
| `finreport/reporting/build.py` | `build_report()` — runs the agent loop |
| `finreport/reporting/writer.py` | writes the `.md` + `.json` |
| `finreport/reporting/charts.py` | ECharts chart builders |
| `finreport/reporting/checks.py` | completeness gates |
| `finreport/ui/app.py` | Streamlit page shell |
| `finreport/ui/render.py` | the report dashboard |
| `finreport/i18n.py` | all user-facing text, per language |
```

Also in `README.md`, update the Tests block's module names to the renamed files:
`tests.test_checks`, `tests.test_market_data`, `tests.test_build`, `tests.test_queue`, `tests.test_writer`, `tests.test_web_search`, `tests.test_loop`.

In `ARCHITECTURE.md`, in the "What each file does" section, update each bolded filename to its new path (`**agent_loop.py**` → `**finreport/agent/loop.py**`, `**data_source.py**` → `**finreport/tools/market_data.py**`, `**web_search.py**` → `**finreport/tools/web_search.py**`, `**financials.py**` → `**finreport/reporting/checks.py**`, `**pipeline.py**` → `**finreport/reporting/build.py**`, `**agent.py**` → `**finreport/jobs/queue.py**`, `**jobs.py**` → `**finreport/jobs/store.py**`, `**report.py**` → `**finreport/reporting/writer.py**`, `**app.py**` → `**finreport/ui/app.py**` (note the dashboard is now `finreport/ui/render.py`), `**charts.py**` → `**finreport/reporting/charts.py**`, `**config.py**` → `**finreport/agent/prompts.py**`, `**model.py**` → `**finreport/agent/model.py**`, `**i18n.py**` → `**finreport/i18n.py**`). Leave the surrounding prose describing what each module does unchanged.

Also in `ARCHITECTURE.md`, replace the "Dependency flow (one direction)" line with:

```markdown
Dependency flow (one direction):
`i18n / agent (prompts, model, loop) ← tools ← reporting ← jobs ← ui`
(entry shims `app.py` / `agent.py` sit at the root and call into the package)
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move the UI into the package and split out the dashboard

finreport/ui/app.py keeps the page shell; render_report moves to
finreport/ui/render.py. A thin root app.py calls ui.app.main(), so
'streamlit run app.py' is unchanged. README + ARCHITECTURE updated to the new
module paths.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 9: Manual check (report to the user, do not skip)**

Run: `./.venv/bin/streamlit run app.py` and confirm the page loads, the Jobs and Reports tabs render, and opening a report draws the dashboard. Stop the server afterwards. If it fails, the cause is in Step 3's `main()` wrapping or Step 2's extraction — fix there, do not change any UI logic.

---

## Self-Review

**1. Spec coverage:**
- Target structure (`finreport/` with agent/tools/jobs/reporting/ui + i18n) → Tasks 1–3. ✓
- Entry shims keeping both commands unchanged → Task 2 Step 6 (`agent.py`), Task 3 Step 4 (`app.py`). ✓
- `schemas.py` deleted → Task 1 Step 2. ✓
- `app.py` split into shell + `render_report` → Task 3 Steps 2–3. ✓
- Tests stay flat, renamed, imports-only changes → Task 1 Step 6, Task 2 Step 8. ✓
- `ROOT` constant + re-anchoring `.env` (×2), `jobs.json`, `reports/` → Task 1 Steps 1 & 4, Task 2 Step 3, verified in Task 2 Step 9. ✓
- Behavior preservation (suite green after every task) → Task 1 Step 7, Task 2 Step 9, Task 3 Step 5. ✓
- Docs updated → Task 3 Step 7. ✓
- `git mv` used for every move → Tasks 1–3 move steps. ✓

**2. Placeholder scan:** No TBD/TODO. Every code step shows the exact code or the exact old→new lines; every command has expected output. The two "move this function unchanged" steps name the exact function and its boundaries rather than re-pasting 120 lines, which is the accurate instruction for a move. ✓

**3. Type consistency:** Module paths and symbol names are identical across tasks: `finreport.agent.loop.run_agent` (Task 1) is what `finreport.reporting.build` imports (Task 2); `finreport.jobs.queue.{queue_jobs, refresh_jobs, clear_finished_jobs, store, main}` (Task 2) is what root `agent.py` and `finreport/ui/app.py` import (Tasks 2–3); `finreport.reporting.writer.REPORTS_DIR` (Task 2) is what the UI imports (Task 3); `finreport.ROOT` (Task 1) is used in Tasks 1–2. `render_report(data)` and `main()` signatures match between definition and shim. ✓

## Out of Scope (do NOT do)

Deep multi-package layouts (`core/`, `domain/`, `infra/`); renaming public functions; changing prompts, the report shape, or chart behavior; adding new tests beyond the renames; touching the dated spec/plan files in `docs/superpowers/`.
