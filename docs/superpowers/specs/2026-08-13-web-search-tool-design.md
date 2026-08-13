# Web Search Tool — Design

**Date:** 2026-08-13
**Status:** Approved, implementing

## Problem

Context gathering (`gather_context` in `research.py`) is a single Gemini call
that uses the **Google Search grounding** tool. Grounding is a separate, per-model
free-tier quota that is easily and repeatedly exhausted (429), and it blocks the
*entire* report build because every report needs one grounded call. Grounding
also gives no control over which sources are used — a stated project goal is to
steer toward authoritative sources and away from brokerage forecasts / user-upload
sites.

## Goal

Decouple **finding** from **writing**. A dedicated web-search tool (Tavily)
retrieves content using its own quota; a plain (non-grounded) Gemini call
synthesizes that content into the existing 8-section context format. This removes
Gemini grounding from the path entirely and gives control over sources.

## Principle

The data source owns the numbers (yfinance); **the search tool owns retrieval
(Tavily)**; a plain writer owns synthesis. Same separation the project already
follows for numbers vs. narrative — now applied to retrieval vs. synthesis.

## Design

### New module: `web_search.py`

Isolates the provider behind one function, the way `data_source.py` isolates
yfinance and `jobs.py` isolates storage — swapping Tavily later touches only
this file.

```python
def search(query: str, max_results: int = 5,
           exclude_domains: list[str] | None = None) -> list[dict]:
    """Web search via Tavily. Returns [{title, uri, content}] (possibly empty).

    Reads TAVILY_API_KEY from the environment. Returns [] on any failure or when
    the key is absent — callers degrade gracefully (same contract as
    fetch_financials returning {}).
    """
```

- Wraps `tavily.TavilyClient(api_key).search(query, max_results=..., search_depth="advanced", exclude_domains=...)`.
- Maps each Tavily result `{title, url, content}` → our `{title, uri, content}`.
- If `TAVILY_API_KEY` is unset → return `[]` immediately (no call). This is the
  "return empty if no key" decision: no fallback to Gemini grounding, so we stay
  off the grounding quota entirely.
- Exact Tavily SDK signatures confirmed against current Tavily docs at
  implementation time.

### Changed flow: `gather_context(company)` — signature unchanged

Still `gather_context(company) -> (text, sources)`, so `pipeline.py` and all
downstream code (writer, report, dashboard) are untouched.

```
company
  → 2 queries from SEARCH_QUERY_TEMPLATES:
       Q1: financials + business + revenue-by-segment (latest full fiscal year)
       Q2: recent developments + risks + competitors + outlook
  → web_search(each, exclude_domains=EXCLUDE_DOMAINS)
  → dedupe results by uri  → collected results + sources
  → PLAIN Gemini call (no tools): synthesize the 8-section format FROM the results
  → return (synthesized_text, sources)
```

- **2 queries per report** (the chosen coverage/usage balance): ~2 Tavily
  searches per report, well within Tavily's free tier.
- **Sources** = the deduped Tavily result URLs (`[{title, uri}]`), replacing the
  `grounding_metadata` extraction that grounding provided.
- If searching yields no results (empty key, failure, or genuinely nothing) →
  return `("", [])`. The writer still runs on the yfinance numbers, and
  `has_usable_financials` still gates on those numbers, so the report degrades
  gracefully exactly as today.

### Prompts (`config.py`)

- `SEARCH_PROMPT` keeps the 8-section format but is reworded from
  *"Search the web and gather…"* → *"Using ONLY the search results below,
  compile…"*. Results are appended after the prompt (same pattern as
  `WRITER_PROMPT` + context). If a section is uncovered by the results, the model
  says so rather than inventing.
- Add `SEARCH_QUERY_TEMPLATES: list[str]` — the two query strings, `{company}`
  filled in — so coverage is tunable in one place.
- Add `EXCLUDE_DOMAINS: list[str]` — known low-quality figure sources to exclude
  (e.g. `studocu.com`, `scribd.com`, `coursehero.com`). Small, curated; can grow
  later. Serves the authoritative-sources goal.

### Config / dependencies / environment

- `requirements.txt`: add `tavily-python`.
- `.env.example`: add `TAVILY_API_KEY=` with a one-line comment.
- The Gemini grounding tool call (`tools=[google_search]`) is **removed** from
  `gather_context`; the synthesis call is a plain schema-less text call.

### Error handling

Every external failure degrades to empty, never raises:
- Missing `TAVILY_API_KEY` → `search()` returns `[]`.
- Tavily error / timeout → `search()` returns `[]`.
- No results → `gather_context` returns `("", [])`.
- The synthesis Gemini call failing is caught by the existing per-job
  `try/except` in `refresh_jobs` (job left `running` to retry).

## Testing

- `test_research.py` (new): stub `web_search` and the Gemini client; assert
  `gather_context`
  - issues 2 queries built from `SEARCH_QUERY_TEMPLATES`,
  - dedupes results by `uri`,
  - passes `EXCLUDE_DOMAINS` through to `search`,
  - returns synthesized text + carried-through sources,
  - returns `("", [])` when `web_search` yields nothing.
- `test_web_search.py` (new, optional): stub the Tavily client; assert the
  result mapping (`url`→`uri`) and the empty-key / error → `[]` paths.
- `test_pipeline.py`: unchanged — it already stubs `gather_context`.

## What stays the same

yfinance numbers, `write_narrative` (the writer), `schemas.py`, `charts.py`, the
job queue, `report.py`, and the whole Streamlit dashboard. This is a contained
swap of *how context is gathered*, behind an unchanged `gather_context` contract.

## Out of scope (YAGNI for v1)

- Region-aware source *inclusion* lists (VN vs. US authoritative sites).
- Fetching/parsing full page bodies beyond what Tavily returns.
- A configurable provider switch (Tavily is hardcoded; the `web_search.py`
  boundary already makes a later swap cheap).
- Keeping Gemini grounding as a fallback path.

## Risks

- **Synthesis quality** — grounding did retrieval + relevance + citation in one
  integrated step; a search-then-synthesize pipeline is only as good as the query
  coverage and how much Tavily content is fed to the model. Mitigation: 2 targeted
  queries + `search_depth="advanced"`; tune `SEARCH_QUERY_TEMPLATES` if coverage
  is thin.
- **Another key/dependency** — one new API key (`TAVILY_API_KEY`) and one new
  dependency (`tavily-python`) to manage.
