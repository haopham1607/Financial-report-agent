# Agentic Report Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `build_report`'s fixed pipeline with a hand-built tool-calling agent loop where the model chooses tools (`resolve_ticker`, `fetch_financials`, `web_search`) and calls `submit_report` when done.

**Architecture:** A new `agent_loop.py` holds the loop, the Gemini function-call tool schemas, and tool dispatch. `run_agent(company)` drives the loop, stamps the authoritative yfinance numbers into the result, and returns the **same report dict shape** as today — so `report.py`, `charts.py`, `app.py`, `schemas.py`, `jobs.py`, `agent.py`, and the dashboard are untouched. `pipeline.build_report` becomes a thin wrapper; `research.gather_context`/`write_narrative` are retired.

**Tech Stack:** Python 3, `google-genai` (function calling via `types.FunctionDeclaration`), the existing `data_source` + `web_search` tools, the project's plain-assert test files.

## Global Constraints

- **Tests are plain-assert files in the `tests/` package.** Run one with `./.venv/bin/python -m tests.test_<name>`, the whole suite with `./.venv/bin/python -m tests`. Copy the runner footer verbatim from an existing test (e.g. `tests/test_financials.py`).
- **`build_report(company: str) -> dict`** signature and the returned **report dict shape are unchanged** (keys: `summary, verdict, health, currency_unit, financials, margins, balance_sheet, cash_flow, segments, segment_period, highlights, risks, context, sources`).
- **Numbers are authoritative:** the `fetch_financials` result is stamped into the report **last** (`report.update(numbers)`), so the model cannot overwrite figures.
- **`MAX_STEPS = 8`** caps the loop.
- **Use the venv:** `./.venv/bin/python` / `./.venv/bin/pip`.
- **Every commit message ends with:** `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Work from the project root: `Financial_report_agent/`.

---

### Task 1: `agent_loop.py` — the tool-calling loop (additive; nothing breaks yet)

**Files:**
- Modify: `config.py` (add `AGENT_PROMPT`; leave the old prompts in place for now)
- Create: `agent_loop.py`
- Create: `tests/test_agent_loop.py`

**Interfaces:**
- Consumes: `data_source.resolve_ticker(name) -> str|None`, `data_source.fetch_financials(ticker) -> dict`, `web_search.search(query, max_results=5, exclude_domains=None) -> list[dict]`, `config.AGENT_PROMPT`, `config.EXCLUDE_DOMAINS`, `model.MODEL`/`model.client`.
- Produces: `run_agent(company: str) -> dict` (the report dict); module globals `MAX_STEPS`, `_model_turn(contents) -> (model_content, list[(name, args)])`, `_dispatch(name, args) -> dict` (all monkeypatched in tests).

- [ ] **Step 1: Add `AGENT_PROMPT` to `config.py`**

Append to the end of `config.py`:

```python
# Agent prompt. Drives the hand-built tool-calling loop in agent_loop.py: the
# model is given tools and this goal, and decides what to call. {company} is
# filled in; REPORT_LANGUAGE is concatenated.
AGENT_PROMPT = (
    '''You are a financial-analysis agent building a financial-HEALTH report for \
the company "{company}". This is a health assessment, NOT investment advice — no \
buy/sell calls or price targets.

Tools available to you:
- resolve_ticker(company_name): get the Yahoo Finance ticker. Call this FIRST.
- fetch_financials(ticker): get the authoritative numbers (revenue, margins, \
balance sheet, cash flow). These numbers are the SOURCE OF TRUTH — never invent \
or alter figures.
- web_search(query): find qualitative context (business, segments, recent \
developments, outlook, competitors, risks). Call it several times with focused \
queries; include the ticker in queries to disambiguate same-named companies.
- submit_report(...): submit the finished report. Call it exactly once, when you \
have the numbers and enough context.

How to proceed: resolve the ticker; if the name is ambiguous or the result looks \
wrong, re-resolve with a more specific name. Fetch the financials. Search the web \
for context. Then call submit_report with: a 3-5 sentence summary of financial \
health (profitability, liquidity & solvency, cash flow); a one-line verdict; \
health ("good"/"mixed"/"weak"); the revenue-by-segment breakdown (list the \
disclosed segments — if they cover less than the whole company, add a final \
segment named "Khác" ("Other") for the remaining share so the pieces sum to the \
whole; state which period they cover in segment_period); highlights; risks; and \
analysis (the qualitative write-up under standard equity-research headings).

Write summary, verdict, highlights, risks, segment names, segment_period, and \
analysis in '''
    + REPORT_LANGUAGE
    + '''.'''
)
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_agent_loop.py`:

```python
"""Tests for agent_loop.run_agent — the hand-built tool-calling loop.
Run: python -m tests.test_agent_loop

Plain asserts, no framework. The model turn (_model_turn) and the tool
implementations are monkeypatched, so no real API / network is used.
"""

import agent_loop


def _script(turns):
    """Return a _model_turn stub yielding scripted turns.

    `turns` is a list of turns; each turn is a list of (tool_name, args) the
    'model' calls that step. The model content is a throwaway placeholder (the
    real loop appends it to `contents`, which the stub then ignores).
    """
    seq = iter(turns)

    def stub(contents):
        calls = next(seq)
        return object(), calls

    return stub


def test_happy_path_assembles_report():
    nums = {"currency_unit": "tỷ VNĐ",
            "financials": [{"year": "2025", "revenue": 100.0, "net_income": 10.0}],
            "margins": {"net": 10.0}}
    srch = [{"title": "CafeF", "uri": "http://cafef.vn/x", "content": "rev up"}]
    final = {"summary": "S", "verdict": "V", "health": "good",
             "segments": [{"name": "A", "revenue": 60}],
             "segment_period": "Cả năm 2025",
             "highlights": ["h"], "risks": ["r"], "analysis": "## Business\n..."}
    agent_loop._model_turn = _script([
        [("resolve_ticker", {"company_name": "X"})],
        [("fetch_financials", {"ticker": "TST"})],
        [("web_search", {"query": "X revenue"})],
        [("submit_report", final)],
    ])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: nums
    agent_loop.search = lambda query, exclude_domains=None: srch

    report = agent_loop.run_agent("X")
    assert report["summary"] == "S" and report["health"] == "good"
    assert report["context"] == "## Business\n..."            # analysis -> context
    assert report["segments"] == [{"name": "A", "revenue": 60}]
    assert report["segment_period"] == "Cả năm 2025"
    assert report["sources"] == [{"title": "CafeF", "uri": "http://cafef.vn/x"}]
    assert report["currency_unit"] == "tỷ VNĐ"               # numbers stamped
    assert report["financials"][0]["revenue"] == 100.0


def test_numbers_are_authoritative():
    # submit_report tries to sneak in numbers; the fetch_financials numbers win.
    nums = {"currency_unit": "USD billion",
            "financials": [{"year": "2025", "revenue": 500.0, "net_income": 50.0}]}
    final = {"summary": "S", "verdict": "V", "health": "good", "analysis": "a",
             "currency_unit": "FAKE", "financials": [{"year": "1999", "revenue": 1}]}
    agent_loop._model_turn = _script([
        [("fetch_financials", {"ticker": "TST"})],
        [("submit_report", final)],
    ])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: nums
    agent_loop.search = lambda query, exclude_domains=None: []

    report = agent_loop.run_agent("X")
    assert report["currency_unit"] == "USD billion"
    assert report["financials"][0]["revenue"] == 500.0


def test_dedupes_sources_across_searches():
    dup = {"title": "D", "uri": "http://a.com", "content": "x"}
    only = {"title": "O", "uri": "http://b.com", "content": "y"}
    agent_loop._model_turn = _script([
        [("web_search", {"query": "q1"})],
        [("web_search", {"query": "q2"})],
        [("submit_report",
          {"summary": "", "verdict": "", "health": "mixed", "analysis": "a"})],
    ])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: {}
    _results = iter([[dup], [dup, only]])
    agent_loop.search = lambda query, exclude_domains=None: next(_results)

    report = agent_loop.run_agent("X")
    assert [s["uri"] for s in report["sources"]] == ["http://a.com", "http://b.com"]


def test_max_steps_without_submit_returns_best_effort():
    # The model never submits (always searches). The loop must stop, not hang.
    agent_loop._model_turn = _script(
        [[("web_search", {"query": "q"})] for _ in range(agent_loop.MAX_STEPS + 2)])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: {}
    agent_loop.search = lambda query, exclude_domains=None: []

    report = agent_loop.run_agent("X")   # must return
    assert report["summary"] == ""       # best-effort empty narrative
    assert report["health"] == "mixed"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}  {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `./.venv/bin/python -m tests.test_agent_loop`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_loop'`.

- [ ] **Step 4: Implement `agent_loop.py`**

Create `agent_loop.py`:

```python
"""A hand-built tool-calling agent loop that builds one company's report.

The model is given four tools and a goal (AGENT_PROMPT); it decides which to call
and in what order, and calls submit_report when done. Code owns two invariants:
the yfinance numbers are stamped in last (authoritative), and the returned dict is
the same shape the rest of the app already consumes.
"""

from google.genai import types

from config import AGENT_PROMPT, EXCLUDE_DOMAINS
from data_source import fetch_financials, resolve_ticker
from model import MODEL, client
from web_search import search

MAX_STEPS = 8

# --- tool schemas (what the model sees it can call) -----------------------

_TOOLS = [types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="resolve_ticker",
        description="Resolve a company name to its Yahoo Finance ticker "
                    "(e.g. 'Vinamilk' -> 'VNM.VN'). Call this first.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"company_name": types.Schema(type=types.Type.STRING)},
            required=["company_name"]),
    ),
    types.FunctionDeclaration(
        name="fetch_financials",
        description="Fetch authoritative financials (revenue, margins, balance "
                    "sheet, cash flow) from Yahoo Finance for a ticker. These "
                    "numbers are the source of truth — never invent figures.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"ticker": types.Schema(type=types.Type.STRING)},
            required=["ticker"]),
    ),
    types.FunctionDeclaration(
        name="web_search",
        description="Search the web for qualitative context. Returns results with "
                    "title, uri, content. Call several times with focused queries.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"query": types.Schema(type=types.Type.STRING)},
            required=["query"]),
    ),
    types.FunctionDeclaration(
        name="submit_report",
        description="Submit the finished financial-health report. Call once.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "summary": types.Schema(type=types.Type.STRING),
                "verdict": types.Schema(type=types.Type.STRING),
                "health": types.Schema(type=types.Type.STRING,
                                       enum=["good", "mixed", "weak"]),
                "segments": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.OBJECT, properties={
                        "name": types.Schema(type=types.Type.STRING),
                        "revenue": types.Schema(type=types.Type.NUMBER)})),
                "segment_period": types.Schema(type=types.Type.STRING),
                "highlights": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING)),
                "risks": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING)),
                "analysis": types.Schema(type=types.Type.STRING),
            },
            required=["summary", "verdict", "health", "analysis"]),
    ),
])]

_NARRATIVE_KEYS = ("summary", "verdict", "health", "segments",
                   "segment_period", "highlights", "risks")


# --- one model turn + tool dispatch ---------------------------------------

def _model_turn(contents):
    """Call the model once. Return (model_content, [(name, args_dict), ...])."""
    resp = client.models.generate_content(
        model=MODEL, contents=contents,
        config=types.GenerateContentConfig(tools=_TOOLS))
    content = resp.candidates[0].content
    calls = []
    for part in (content.parts or []):
        fc = getattr(part, "function_call", None)
        if fc:
            calls.append((fc.name, dict(fc.args or {})))
    return content, calls


def _dispatch(name, args):
    """Run a non-terminal tool; return a JSON-serialisable dict result."""
    if name == "resolve_ticker":
        return {"ticker": resolve_ticker(args.get("company_name", ""))}
    if name == "fetch_financials":
        return fetch_financials(args.get("ticker", "")) or {}
    if name == "web_search":
        return {"results": search(args.get("query", ""),
                                  exclude_domains=EXCLUDE_DOMAINS)}
    return {"error": f"unknown tool {name}"}


# --- the loop -------------------------------------------------------------

def run_agent(company: str) -> dict:
    """Drive the tool-calling loop for one company; return the report dict."""
    contents = [types.Content(
        role="user",
        parts=[types.Part(text=AGENT_PROMPT.format(company=company))])]
    numbers, sources, seen = {}, [], set()
    final = None

    for _ in range(MAX_STEPS):
        content, calls = _model_turn(contents)
        contents.append(content)
        if not calls:
            contents.append(types.Content(role="user", parts=[types.Part(
                text="Call a tool, or submit_report when you have enough.")]))
            continue
        for name, args in calls:
            if name == "submit_report":
                final = args
                break
            result = _dispatch(name, args)
            if name == "fetch_financials":
                numbers = result or {}
            elif name == "web_search":
                for r in result.get("results", []):
                    uri = r.get("uri")
                    if uri and uri not in seen:
                        seen.add(uri)
                        sources.append({"title": r.get("title") or uri, "uri": uri})
            contents.append(types.Content(role="tool", parts=[
                types.Part.from_function_response(name=name, response=result)]))
        if final is not None:
            break

    return _assemble(final, numbers, sources)


def _assemble(final, numbers, sources) -> dict:
    """Combine the agent's narrative with the authoritative numbers + sources."""
    report = {}
    if final:
        for k in _NARRATIVE_KEYS:
            report[k] = final.get(k)
        report["context"] = final.get("analysis", "")
    else:  # hit MAX_STEPS without submitting — best-effort empty narrative
        report.update({"summary": "", "verdict": "", "health": "mixed",
                       "segments": [], "segment_period": "",
                       "highlights": [], "risks": [], "context": ""})
    report["sources"] = sources
    report.update(numbers)   # yfinance numbers stamped LAST — authoritative
    return report
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/bin/python -m tests.test_agent_loop`
Expected: PASS — `4/4 passed`.

- [ ] **Step 6: Commit**

```bash
git add config.py agent_loop.py tests/test_agent_loop.py
git commit -m "feat: hand-built tool-calling agent loop (agent_loop.run_agent)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Wire the loop into `build_report` and retire the old workflow

**Files:**
- Modify: `tests/test_pipeline.py` (replace old stubs with a `run_agent` stub)
- Modify: `pipeline.py` (`build_report` → `run_agent`)
- Delete: `research.py`, `tests/test_research.py`
- Modify: `config.py` (remove `SEARCH_PROMPT`, `WRITER_PROMPT`, and the now-unused `SEARCH_QUERY_TEMPLATES`; keep `REPORT_LANGUAGE`, `AGENT_PROMPT`, `EXCLUDE_DOMAINS`)

**Interfaces:**
- Consumes: `agent_loop.run_agent(company) -> dict` (Task 1).
- Produces: `pipeline.build_report(company) -> dict` (unchanged signature), delegating to `run_agent`.

Note: `SEARCH_QUERY_TEMPLATES` is removed because its only consumer was the retired `research.gather_context`; the agent forms its own queries. This refines the spec's "keep it" note (dead config otherwise). `EXCLUDE_DOMAINS` stays — `agent_loop._dispatch` passes it to `web_search`.

- [ ] **Step 1: Replace `tests/test_pipeline.py`**

Overwrite `tests/test_pipeline.py` with:

```python
"""Tests for pipeline.build_report — now a thin wrapper over the agent loop.
Run: python -m tests.test_pipeline

Plain asserts, no framework. run_agent is stubbed, so no real API is used.
"""

import pipeline


def test_build_report_delegates_to_run_agent():
    seen = {}

    def fake_run_agent(company):
        seen["company"] = company
        return {"summary": "S", "health": "good",
                "financials": [{"year": "2025", "revenue": 100.0}]}

    saved = pipeline.run_agent
    pipeline.run_agent = fake_run_agent
    try:
        data = pipeline.build_report("FPT")
    finally:
        pipeline.run_agent = saved

    assert seen["company"] == "FPT"
    assert data["summary"] == "S"
    assert data["financials"][0]["revenue"] == 100.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}  {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m tests.test_pipeline`
Expected: FAIL — `AttributeError: module 'pipeline' has no attribute 'run_agent'` (build_report still imports/uses `research`).

- [ ] **Step 3: Rewrite `pipeline.py`**

Overwrite `pipeline.py` with:

```python
"""Build a structured report by running the tool-calling agent loop.

Kept as a thin, separately-testable wrapper over agent_loop.run_agent so the job
queue depends on a stable build_report(company) -> dict contract.
"""

from agent_loop import run_agent


def build_report(company: str) -> dict:
    """Build the report dict for one company via the agent loop."""
    return run_agent(company)
```

- [ ] **Step 4: Delete the retired files**

Run:
```bash
git rm research.py tests/test_research.py
```
Expected: both files removed.

- [ ] **Step 5: Remove the retired prompts/config from `config.py`**

In `config.py`, delete the entire `SEARCH_PROMPT = ( ... )` block and the entire
`WRITER_PROMPT = ( ... )` block, and delete the `SEARCH_QUERY_TEMPLATES = [ ... ]`
list. Keep `REPORT_LANGUAGE`, `AGENT_PROMPT`, and `EXCLUDE_DOMAINS`. Verify no
other file imports the removed names:

Run:
```bash
grep -rn "SEARCH_PROMPT\|WRITER_PROMPT\|SEARCH_QUERY_TEMPLATES\|gather_context\|write_narrative" --include=*.py .
```
Expected: no matches (outside the plan/docs). If any appear, fix that import.

- [ ] **Step 6: Run the pipeline test, then the full suite**

Run: `./.venv/bin/python -m tests.test_pipeline`
Expected: PASS — `1/1 passed`.

Run: `./.venv/bin/python -m tests`
Expected: every module PASS — `All test modules passed.` (Modules now: test_agent, test_agent_loop, test_data_source, test_financials, test_pipeline, test_report, test_web_search.)

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: build_report runs the agent loop; retire the fixed workflow

pipeline.build_report now delegates to agent_loop.run_agent. Deletes research.py
(gather_context/write_narrative) and its test, and removes SEARCH_PROMPT /
WRITER_PROMPT / SEARCH_QUERY_TEMPLATES from config. Report dict shape and the
build_report contract are unchanged, so the dashboard/charts/report writer/job
queue are untouched.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- New `agent_loop.py` with `run_agent` + the loop → Task 1. ✓
- Four tools (`resolve_ticker`, `fetch_financials`, `web_search`, `submit_report`) as `FunctionDeclaration`s → Task 1 `_TOOLS`. ✓
- Hand-built loop with `MAX_STEPS`, tool dispatch, accumulate numbers/sources, end on `submit_report` → Task 1 `run_agent`. ✓
- Numbers authoritative (`report.update(numbers)` last) → Task 1 `_assemble`; verified by `test_numbers_are_authoritative`. ✓
- Output shape unchanged; `build_report` delegates → Task 2. ✓
- `AGENT_PROMPT` added; `SEARCH_PROMPT`/`WRITER_PROMPT` retired → Tasks 1 & 2. ✓
- `research.gather_context`/`write_narrative` retired (`research.py` deleted) → Task 2. ✓
- Tests: new `test_agent_loop.py` (happy path, numbers-authoritative, dedupe/self-correction via repeated calls, MAX_STEPS); `test_research.py` removed; `test_pipeline.py` updated → Tasks 1 & 2. ✓
- `web_search.py`, `schemas.py`, `charts.py`, `report.py`, `app.py`, `jobs.py`, `agent.py` untouched. ✓
- Guardrail / graceful degrade (MAX_STEPS → best-effort dict; existing usable-financials gate) → Task 1 `_assemble`; `test_max_steps_without_submit_returns_best_effort`. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every test step shows the asserts; commands have expected output. ✓

**3. Type consistency:** `run_agent(company) -> dict` defined in Task 1, consumed in Task 2. `_model_turn(contents) -> (content, [(name, args)])`, `_dispatch(name, args) -> dict`, `MAX_STEPS`, and the monkeypatched names (`resolve_ticker`, `fetch_financials`, `search`, `_model_turn`) match between `agent_loop.py` and `tests/test_agent_loop.py`. Report keys in `_assemble` match the Global-Constraints shape. ✓

## Out of Scope (from spec, do NOT build)

Keeping the old workflow alongside; conversational follow-ups; tools beyond the four; parallel tool-call handling (calls are dispatched sequentially).
