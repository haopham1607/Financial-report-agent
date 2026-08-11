# Grounded-Narrative Pipeline — Design

**Date:** 2026-08-06
**Status:** Implemented

> This doc records the design and its rationale; the sections below have been
> reconciled with the shipped code. As-built naming: the two model calls are
> `gather_context(company)` (grounded search) and
> `write_narrative(company, numbers, context)` (the schema-enforced writer) in
> `research.py`; the job-queue entry point is `queue_jobs(companies)` in
> `agent.py`; the carried-through analysis text is the `context` field.

## Problem

After Tier 1, the deep-research agent is disproportionate: it takes ~11 minutes
and the full async job machinery, but we only use it for the **narrative +
segments** (numbers come from yfinance). Worse, its narrative reasons over the
numbers *it* found, which can disagree with the yfinance numbers we display.

## Goal

Replace the deep-research agent with a fast **Google-Search-grounded model call**
that writes the analysis **from the yfinance numbers** (+ current web context).
This makes the narrative consistent with the charts, produces cited sources, and
cuts the slow step from ~11 min to ~seconds.

## Key finding (spike, 2026-08-06)

- Google Search grounding works and returns **cited web sources**
  (`grounding_metadata.grounding_chunks[].web`).
- Grounding **cannot** be combined with `response_schema` (API rejects it).
- Therefore the analysis is **two steps**: a grounded free-text call
  (`gather_context`), then a schema-enforced writer call (`write_narrative`) to
  structure it.

(The running model is `gemini-3.6-flash`, from `model.py` / `RISK_AGENT_MODEL`.)

## Design

### `gather_context(company) -> (text, sources)` (`research.py`)
One grounded `generate_content` call (`tools=[google_search]`), given the
company name only, asked to gather qualitative context in a fixed format
(business, segments, developments, outlook, competitors, risks) — see
`SEARCH_PROMPT`. Returns the context text plus the cited sources
(`[{title, uri}]`) pulled from `grounding_metadata`. It does *not* see the
numbers; it only finds information.

### `write_narrative(company, numbers, context) -> dict` (`research.py`)
A plain (no-tools), schema-enforced call (`response_schema=NarrativeReport`)
that fuses the actual yfinance numbers (the source of truth) with the gathered
context into the structured report fields (`summary`, `verdict`, `health`,
`segments`, `highlights`, `risks`) — see `WRITER_PROMPT`. Splitting gathering
from writing is what sidesteps the grounding-vs-schema limitation.

### `build_report(company)` (`pipeline.py`)
```
numbers = fetch_financials(resolve_ticker(company))          # yfinance
context, sources = gather_context(company)                   # grounded call
data = write_narrative(company, numbers, context)            # writer → structured
data.update(numbers)                                         # yfinance owns numbers
data["context"], data["sources"] = context, sources          # for display
return data
```
No deep research, no LLM number-fallback: numbers are yfinance-only. A company
with no yfinance data yields the existing "incomplete" flag.

### Execution model — process-on-poll (`agent.py`)
The slow, Google-hosted interaction is gone, so there is nothing to poll. The
job queue is kept for batching, persistence and retries, but the work now runs
locally:
- `queue_jobs(companies)` — create Jobs in state `running` (no
  interaction id).
- `refresh_jobs()` — for each `running` job, run `build_report` + `write_report`,
  mark `done`. Reuses the existing per-job `try/except` resilience (a failure
  leaves the job `running` to retry).

Trade-off: `refresh` now does the work, so it blocks for the (bounded, ~seconds)
processing rather than being an instant status check. Given the work is now
fast, this is acceptable; a true non-blocking background (threads/subprocess) is
a possible follow-up.

### Config (`config.py`)
`RESEARCH_PROMPT` / `RESEARCH_PROMPT_FULL` are retired; the two prompts are
`SEARCH_PROMPT` (the fixed gather format for `gather_context`) and
`WRITER_PROMPT` (fuse numbers + context → report, for `write_narrative`), both
written in `REPORT_LANGUAGE`.

### Display (`app.py`, `report.py`)
The report shows the gathered analysis (the `context` field), with a short
**Sources** list (the cited links) beneath it.

## Removed

`start_research`, `check_research` (deep research), `extract_financials`,
`reextract_field` (the LLM number fallback), and their prompts. `Job.interaction_id`
becomes vestigial (kept as `""` for storage compatibility, or dropped).

## Testing

- `test_pipeline.py` — stub `gather_context` + `write_narrative` +
  yfinance; assert numbers from yfinance, narrative from the writer, context and
  sources carried through.
- `test_agent.py` — unchanged shape (stubs `build_report`).
- `test_financials.py`, `test_data_source.py` — unchanged.
- Live validation deferred until Gemini quota resets (today's is exhausted).

## Risks

- **Execution blocking** — `refresh` blocks during processing (bounded); true
  background is a follow-up.
- **Grounding quota/latency** — grounded calls are heavier than plain ones; the
  resilience path keeps a rate-limited job to retry.
- **No number fallback** — a company absent from yfinance gets no numbers (the
  incomplete flag), where before the LLM could try the prose.
