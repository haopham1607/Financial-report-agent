# Agentic Report Loop — Design

**Date:** 2026-08-13
**Status:** Approved, implementing

## Problem

The report is built by a **fixed pipeline** (`pipeline.build_report`): a hardcoded
sequence `resolve_ticker → fetch_financials → gather_context → write_narrative`.
The LLM only fills predefined slots; it never decides what to do. That makes it a
*workflow*, not an *agent*. The goal here is to **learn/demonstrate the agent
pattern** by replacing that fixed sequence with a hand-built tool-calling loop
where the model chooses its own actions.

## Goal

Replace `build_report`'s internals with a **hand-built agent loop**: the model is
given tools and a goal, and it decides which tools to call, in what order, when to
search again, and when it has enough to finish. Keep the **report output shape
identical** so the rest of the app (dashboard, charts, report writer, job queue,
CLI) is untouched.

## Principles preserved

- **Numbers stay authoritative.** The `fetch_financials` tool returns the
  deterministic yfinance numbers; code stamps *those* into the final report so the
  agent cannot overwrite them with hallucinated figures.
- **Same output contract.** `build_report(company) -> dict` returns the exact same
  report dict as today (numbers + narrative + segments + segment_period + context +
  sources), so `report.py`, `charts.py`, `app.py`, `schemas.py`, `jobs.py`,
  `agent.py`, and the dashboard are unchanged.

## Design

### New module: `agent_loop.py`

Holds the loop, the tool schemas (Gemini `FunctionDeclaration`s), and tool
dispatch. One public entry point:

```python
def run_agent(company: str) -> dict:
    """Drive the tool-calling loop for one company; return the report dict."""
```

### The tools (the agent's capabilities)

Existing building blocks, exposed as Gemini function-calling tools:

| Tool | Args | Returns / effect |
|------|------|------------------|
| `resolve_ticker` | `company_name: str` | `{"ticker": str \| null}` (wraps `data_source.resolve_ticker`) |
| `fetch_financials` | `ticker: str` | the yfinance numbers dict (wraps `data_source.fetch_financials`); the loop remembers this as the authoritative numbers |
| `web_search` | `query: str` | `[{title, uri, content}]` (wraps `web_search.search`, passing `EXCLUDE_DOMAINS`); the loop accumulates the returned sources |
| `submit_report` | `summary, verdict, health, segments, segment_period, highlights, risks, analysis` | records the agent's final answer and **ends the loop** |

`submit_report`'s parameters mirror the `NarrativeReport` schema fields (reused),
plus `analysis` — the 8-section qualitative write-up shown in the dashboard's
"Phân tích" section. `currency_unit` is NOT a `submit_report` arg; it comes from
the numbers.

### The loop (hand-built)

```
contents = [ AGENT_PROMPT with the company name ]
numbers = {}            # set when fetch_financials is called
sources = []            # accumulated from web_search calls (deduped by uri)
final = None            # set when submit_report is called

for step in range(MAX_STEPS):        # MAX_STEPS = 8
    resp = client.models.generate_content(model=MODEL, contents=contents,
                                           config=GenerateContentConfig(tools=TOOLS))
    calls = function calls in resp
    if not calls:
        # model emitted text with no tool call — append a nudge to use a tool /
        # submit_report, then continue
        append the model text + a user nudge to contents; continue
    append the model's function-call content to contents
    for call in calls:
        result = dispatch(call)          # run the wrapped function
        if call.name == "fetch_financials": numbers = result or {}
        if call.name == "web_search":      accumulate result into sources (dedupe uri)
        if call.name == "submit_report":   final = call.args; break the loop
        append Part.from_function_response(call.name, result) to contents

assemble and return the report dict (below)
```

**Gemini mechanics (google-genai):** tools are `types.Tool(function_declarations=[...])`;
each turn's model content (carrying `function_call` parts) is appended to
`contents`, followed by a `types.Content` with `Part.from_function_response(...)`
per call, so the model sees each result on the next turn.

### Assembling the final report dict

```
report = { **final_narrative_fields }          # summary, verdict, health,
                                               # segments, segment_period,
                                               # highlights, risks
report["context"] = final["analysis"]
report["sources"] = sources                    # deduped web_search sources
report.update(numbers)                          # yfinance stamps the authoritative
                                               # numbers LAST (financials, margins,
                                               # balance_sheet, cash_flow, currency_unit)
return report
```

If the agent never called `submit_report` (hit `MAX_STEPS`), return a minimal
best-effort dict (`numbers` + empty narrative), which the existing
`has_usable_financials` gate then judges — the job fails cleanly if there's
nothing usable, same as today.

### `pipeline.build_report`

```python
from agent_loop import run_agent

def build_report(company: str) -> dict:
    return run_agent(company)
```

### `config.py`

- Add `AGENT_PROMPT` — the system/goal prompt: the agent's job (build a
  financial-health report for `{company}`), how to use the tools (resolve the
  ticker first, fetch the numbers, search the web for qualitative context,
  re-resolve if the company looks wrong/ambiguous), that the **numbers come from
  `fetch_financials` — never invent them**, that segment figures may be partial
  (list what's found + an "Other/Khác" remainder), state the `segment_period`, and
  call `submit_report` when done. Written in `REPORT_LANGUAGE` for the narrative
  fields.
- Keep `SEARCH_QUERY_TEMPLATES` (the agent can use them as query ideas) and
  `EXCLUDE_DOMAINS` (passed to `web_search`).
- Retire `SEARCH_PROMPT` and `WRITER_PROMPT`.

### Retired

`research.gather_context` and `research.write_narrative` are removed (the loop
replaces them). `research.py` is deleted or reduced to nothing used;
`pipeline.py` no longer imports it. The `NarrativeReport` schema stays (its fields
define `submit_report`'s parameters).

## Guardrails / error handling

- `MAX_STEPS = 8` caps the loop; on exhaustion, finalize best-effort.
- A tool that raises returns an error string to the model (so it can react) rather
  than crashing the loop; `web_search`/`fetch_financials` already degrade to
  `[]`/`{}`.
- The whole `run_agent` runs inside `refresh_jobs`' existing per-job `try/except`,
  so an API error (429/503) leaves the job `running` to retry — unchanged.
- Numbers are stamped by code, so a hallucinated figure from the model can't reach
  the report.

## Testing (`tests/test_agent_loop.py`, new)

Stub the model client AND the tools; no real API:

- **Happy path:** a scripted model that calls `resolve_ticker → fetch_financials →
  web_search → submit_report`. Assert: each tool dispatched with the model's args;
  `numbers` stamped from `fetch_financials`; `sources` accumulated/deduped from
  `web_search`; final dict has narrative fields + `context` from `analysis` + the
  numbers; loop ends on `submit_report`.
- **Numbers authoritative:** `submit_report` with bogus numbers in narrative →
  final dict still shows the `fetch_financials` numbers.
- **Self-correction:** scripted `resolve_ticker` (wrong) → `resolve_ticker`
  (again) → … proves multiple calls to the same tool are handled.
- **MAX_STEPS:** a model that never submits → loop stops at `MAX_STEPS` and returns
  a best-effort dict (no infinite loop).

`test_pipeline.py` is updated/replaced (its `gather_context`/`write_narrative`
stubs no longer exist); `test_research.py`/`test_web_search.py`: `test_research.py`
is removed with `research.py`, `test_web_search.py` stays (web_search is still a
tool). `test_agent.py`, `test_financials.py`, `test_data_source.py`,
`test_report.py` are unchanged.

## What stays the same

yfinance numbers, `web_search.py`, `schemas.py` (`NarrativeReport`), `charts.py`,
`report.py`, `app.py`, `jobs.py`, `agent.py` (job queue + CLI), `i18n.py`, and the
whole dashboard. Only *how the report content is produced* changes.

## Out of scope (YAGNI)

- Keeping the old workflow alongside (we're replacing it).
- Conversational follow-ups / multi-turn user interaction.
- New tools beyond the four (no PDF fetch, no calculator, etc.).
- Parallel tool calls (handle calls sequentially even if the model returns several).

## Risks

- **Reliability vs. the workflow:** an agent is less deterministic; it may search
  redundantly or occasionally not submit. Mitigation: `MAX_STEPS`, code-stamped
  numbers, the existing usable-financials gate, and per-job retry.
- **More model calls:** each step is a model call, so a report costs several calls
  (vs. 3 today) — more exposure to the tight free-tier limits. Mitigation: keep
  `MAX_STEPS` small; the friendly 429/503 handling already added helps.
