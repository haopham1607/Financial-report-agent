# Web Search Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Gemini Search-grounding call in `gather_context` with a dedicated Tavily web-search tool plus a plain-Gemini synthesis step, so context gathering no longer consumes the Gemini grounding quota.

**Architecture:** A new `web_search.py` isolates Tavily behind a `search()` function returning `[{title, uri, content}]` (empty on any failure). `gather_context(company)` runs two configured queries through it, dedupes by URL, and has a plain (non-grounded) Gemini call synthesize the existing 8-section context format from the results. `gather_context` keeps its `(text, sources)` contract, so the pipeline and dashboard are unchanged.

**Tech Stack:** Python 3, `tavily-python` (new), `google-genai` (existing), the project's plain-assert test files.

## Global Constraints

- **Tests are plain-assert files, no framework.** Each `test_*.py` ends with the standard runner footer and is run with `./.venv/bin/python test_<name>.py`. Copy the footer verbatim from an existing test file (e.g. `test_financials.py`).
- **All external failures degrade to empty, never raise:** `search()` returns `[]`; `gather_context()` returns `("", [])`.
- **`gather_context(company: str) -> tuple[str, list[dict]]`** signature must not change (the pipeline depends on it).
- **Use the venv:** all Python commands are `./.venv/bin/python ...` / `./.venv/bin/pip ...`.
- **Every commit message ends with:**
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Work from the project root: `Financial_report_agent/`.

---

### Task 1: `web_search.py` — the Tavily wrapper

**Files:**
- Create: `web_search.py`
- Create: `test_web_search.py`
- Modify: `requirements.txt` (add `tavily-python`)
- Modify: `.env.example` (add `TAVILY_API_KEY`)

**Interfaces:**
- Produces: `search(query: str, max_results: int = 5, exclude_domains: list[str] | None = None) -> list[dict]` where each dict is `{"title": str, "uri": str, "content": str}`. Returns `[]` when `TAVILY_API_KEY` is unset or on any error. Also produces `_client() -> TavilyClient | None` (monkeypatched in tests).

- [ ] **Step 1: Write the failing test**

Create `test_web_search.py`:

```python
"""Tests for web_search.py — the Tavily wrapper. Run: python test_web_search.py

Plain asserts, no test framework. Tavily is never called: tests monkeypatch
_client() with a fake, and the no-key path needs no client at all.
"""

import web_search


class _FakeTavily:
    """Stand-in for TavilyClient; records the kwargs it was called with."""
    def __init__(self, payload):
        self.payload = payload
        self.seen = None

    def search(self, **kwargs):
        self.seen = kwargs
        return self.payload


def _use(fake):
    web_search._client = lambda: fake


# --- mapping Tavily results -> our shape ---

def test_maps_url_to_uri_and_keeps_title_content():
    _use(_FakeTavily({"results": [
        {"title": "FPT Q4", "url": "https://cafef.vn/fpt", "content": "revenue up"},
    ]}))
    out = web_search.search("FPT revenue")
    assert out == [{"title": "FPT Q4", "uri": "https://cafef.vn/fpt",
                    "content": "revenue up"}]


def test_drops_results_without_a_url():
    _use(_FakeTavily({"results": [
        {"title": "no link", "content": "x"},
        {"title": "ok", "url": "https://x.com", "content": "y"},
    ]}))
    out = web_search.search("q")
    assert [r["uri"] for r in out] == ["https://x.com"]


def test_passes_query_and_exclude_domains_to_tavily():
    fake = _FakeTavily({"results": []})
    _use(fake)
    web_search.search("hello", max_results=3, exclude_domains=["scribd.com"])
    assert fake.seen["query"] == "hello"
    assert fake.seen["max_results"] == 3
    assert fake.seen["exclude_domains"] == ["scribd.com"]


# --- graceful degradation ---

def test_no_key_returns_empty(monkeypatch=None):
    web_search._client = lambda: None
    assert web_search.search("anything") == []


def test_tavily_error_returns_empty():
    class _Boom:
        def search(self, **kwargs):
            raise RuntimeError("network down")
    _use(_Boom())
    assert web_search.search("q") == []


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

Run: `./.venv/bin/python test_web_search.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'web_search'` (the module doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `web_search.py`:

```python
"""Web search via Tavily — the retrieval tool.

Isolates the provider behind one function so the rest of the app never imports
Tavily directly (swap the provider by changing only this file). Every failure
degrades to an empty list, so callers never need a try/except.
"""

import os


def _client():
    """A Tavily client, or None when TAVILY_API_KEY is unset.

    Imported lazily so this module (and its no-key path) works even if
    tavily-python is not installed.
    """
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return None
    from tavily import TavilyClient
    return TavilyClient(api_key=key)


def search(query: str, max_results: int = 5,
           exclude_domains: list[str] | None = None) -> list[dict]:
    """Web search → [{title, uri, content}]; [] on missing key or any error."""
    client = _client()
    if client is None:
        return []
    try:
        resp = client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",
            exclude_domains=exclude_domains or [],
        )
    except Exception:
        return []
    results = resp.get("results", []) if isinstance(resp, dict) else []
    out = []
    for r in results:
        uri = r.get("url")
        if not uri:
            continue
        out.append({
            "title": r.get("title") or uri,
            "uri": uri,
            "content": r.get("content", "") or "",
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python test_web_search.py`
Expected: PASS — `5/5 passed`.

- [ ] **Step 5: Add the dependency and env example**

Append `tavily-python` to `requirements.txt` (one line, after `streamlit`/`yfinance`), then install it:

Run: `./.venv/bin/pip install tavily-python`
Expected: installs successfully.

Add to `.env.example` (below the `RISK_AGENT_MODEL` comment):

```
# Tavily web search (context gathering). Get a free key at tavily.com
TAVILY_API_KEY=your-tavily-key-here
```

- [ ] **Step 6: Re-run the test after install (import path still clean)**

Run: `./.venv/bin/python test_web_search.py`
Expected: PASS — `5/5 passed` (the no-key path returns `[]`; no real Tavily call is made).

- [ ] **Step 7: Commit**

```bash
git add web_search.py test_web_search.py requirements.txt .env.example
git commit -m "feat: add Tavily web_search tool (isolated, empty on failure)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `gather_context` uses the tool + config prompts/constants

**Files:**
- Modify: `config.py` (reword `SEARCH_PROMPT`; add `SEARCH_QUERY_TEMPLATES`, `EXCLUDE_DOMAINS`)
- Modify: `research.py` (rewrite `gather_context`)
- Create: `test_research.py`

**Interfaces:**
- Consumes: `web_search.search(query, max_results=5, exclude_domains=None) -> list[dict]` from Task 1.
- Consumes (config, this task): `SEARCH_QUERY_TEMPLATES: list[str]` (each with a `{company}` field), `EXCLUDE_DOMAINS: list[str]`, reworded `SEARCH_PROMPT: str` (has `{company}`).
- Produces: `gather_context(company: str) -> tuple[str, list[dict]]` — unchanged signature; sources are `[{title, uri}]`.

- [ ] **Step 1: Add the config constants and reword SEARCH_PROMPT**

In `config.py`, change the first sentence of `SEARCH_PROMPT` from the "Search the web and gather…" framing to synthesis-from-results framing. Replace this opening line:

```python
    '''Search the web and gather the following about the company "{company}", \
under these EXACT headings. Use actual reported information; clearly label any \
forward-looking figure as a forecast. Be concise and factual.
```

with:

```python
    '''Using ONLY the web search results provided below, compile the following \
about the company "{company}", under these EXACT headings. Use only information \
supported by the results; if the results do not cover a section, say so. Clearly \
label any forward-looking figure as a forecast. Be concise and factual.
```

Then, at the end of `config.py`, add:

```python
# Two web-search queries per company (filled with {company}); their combined
# results feed the SEARCH_PROMPT synthesis. Kept here so coverage is tunable.
SEARCH_QUERY_TEMPLATES = [
    '{company} annual revenue by segment business overview latest fiscal year '
    'financial results',
    '{company} recent developments risks competitors outlook',
]

# Low-quality sources to exclude from search (user-upload / study sites that
# publish unreliable figures). Curated; extend as needed.
EXCLUDE_DOMAINS = ["studocu.com", "scribd.com", "coursehero.com"]
```

- [ ] **Step 2: Write the failing test**

Create `test_research.py`:

```python
"""Tests for research.gather_context — search tool + plain synthesis.
Run: python test_research.py

Plain asserts, no framework. Tavily and Gemini are never called: we monkeypatch
research.search (the web-search tool) and research.client (the model).
"""

import config
import research


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text):
        self._text = text
        self.seen_contents = None

    def generate_content(self, model, contents, config=None):
        self.seen_contents = contents
        return _FakeResp(self._text)


class _FakeClient:
    def __init__(self, text):
        self.models = _FakeModels(text)


def _install(results_for_query, synth_text="SYNTHESIZED"):
    """Point research at fake search + client; return (calls, client)."""
    calls = []

    def fake_search(query, max_results=5, exclude_domains=None):
        calls.append({"query": query, "exclude_domains": exclude_domains})
        for needle, res in results_for_query.items():
            if needle in query:
                return res
        return []

    client = _FakeClient(synth_text)
    research.search = fake_search
    research.client = client
    return calls, client


def test_runs_one_search_per_template_with_exclude_domains():
    calls, _ = _install({"": []})  # "" matches every query -> []
    research.gather_context("FPT")
    assert len(calls) == len(config.SEARCH_QUERY_TEMPLATES)
    for c in calls:
        assert c["exclude_domains"] == config.EXCLUDE_DOMAINS
        assert "FPT" in c["query"]


def test_dedupes_results_by_uri_across_queries():
    dup = {"title": "Dup", "uri": "https://a.com", "content": "x"}
    only = {"title": "Only", "uri": "https://b.com", "content": "y"}
    # First template query returns dup; second returns dup again + only.
    q1 = config.SEARCH_QUERY_TEMPLATES[0].split()[1]  # a word from template 1
    q2 = config.SEARCH_QUERY_TEMPLATES[1].split()[1]  # a word from template 2
    calls, _ = _install({q1: [dup], q2: [dup, only]})
    text, sources = research.gather_context("FPT")
    assert [s["uri"] for s in sources] == ["https://a.com", "https://b.com"]


def test_synthesis_sees_result_content_and_returns_text_and_sources():
    res = [{"title": "CafeF", "uri": "https://cafef.vn/x", "content": "rev grew 20%"}]
    calls, client = _install({"": res}, synth_text="THE ANALYSIS")
    text, sources = research.gather_context("FPT")
    assert text == "THE ANALYSIS"
    assert sources == [{"title": "CafeF", "uri": "https://cafef.vn/x"}]
    assert "rev grew 20%" in client.models.seen_contents  # results fed to model


def test_no_results_returns_empty_and_skips_model():
    calls, client = _install({"": []})
    text, sources = research.gather_context("Nowhere Inc")
    assert text == ""
    assert sources == []
    assert client.models.seen_contents is None  # model never called


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

Run: `./.venv/bin/python test_research.py`
Expected: FAIL — the current `gather_context` calls the real Gemini grounding client (no `research.search` attribute is used yet), so `test_runs_one_search_per_template...` fails (0 calls recorded) and/or an API error is raised.

- [ ] **Step 4: Rewrite `gather_context`**

In `research.py`, update the imports near the top:

```python
from config import SEARCH_PROMPT, WRITER_PROMPT, SEARCH_QUERY_TEMPLATES, EXCLUDE_DOMAINS
from model import MODEL, client
from schemas import NarrativeReport
from web_search import search
```

Replace the entire existing `gather_context` function with:

```python
def gather_context(company: str) -> tuple[str, list[dict]]:
    """Gather qualitative context WITHOUT Gemini grounding.

    Runs the configured web-search queries through the Tavily tool, dedupes the
    results by URL, then has a plain (no-tools) model call synthesize the fixed
    SEARCH_PROMPT format from those results. Returns (context text, sources).
    Returns ("", []) when the search yields nothing (missing key, error, or no
    hits) so the pipeline degrades to numbers-only gracefully.
    """
    results, seen = [], set()
    for template in SEARCH_QUERY_TEMPLATES:
        for r in search(template.format(company=company),
                        exclude_domains=EXCLUDE_DOMAINS):
            uri = r.get("uri")
            if uri and uri not in seen:
                seen.add(uri)
                results.append(r)

    if not results:
        return "", []

    sources = [{"title": r["title"], "uri": r["uri"]} for r in results]
    blob = "\n\n".join(
        f"[{r['title']}] {r['uri']}\n{r['content']}" for r in results)
    prompt = (SEARCH_PROMPT.format(company=company)
              + "\n\n---\nSearch results:\n\n" + blob)
    response = client.models.generate_content(model=MODEL, contents=prompt)
    return response.text or "", sources
```

Note: the `from google.genai import types` import at the top of `research.py` stays — `write_narrative` still uses it. `gather_context` no longer references `types`.

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/bin/python test_research.py`
Expected: PASS — `4/4 passed`.

- [ ] **Step 6: Run the full suite (no regressions)**

Run:
```bash
for t in test_financials.py test_data_source.py test_pipeline.py test_agent.py test_report.py test_web_search.py test_research.py; do ./.venv/bin/python "$t" >/dev/null 2>&1 && echo "PASS $t" || echo "FAIL $t"; done
```
Expected: every line `PASS`. (`test_pipeline.py` still passes because it stubs `gather_context` wholesale.)

- [ ] **Step 7: Commit**

```bash
git add config.py research.py test_research.py
git commit -m "feat: gather_context uses Tavily search + plain synthesis (no grounding)

Two configured queries -> web_search -> dedupe by URL -> plain Gemini synthesis
of the 8-section format. Removes the Gemini Search-grounding quota from the path.
gather_context keeps its (text, sources) contract.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- New `web_search.py` with `search()` + `[]` fallbacks → Task 1. ✓
- `gather_context` rewritten (same signature), 2 queries, dedupe by URL, plain synthesis, sources from results → Task 2. ✓
- Return empty if `TAVILY_API_KEY` missing → Task 1 `_client()` returns None → `search()` returns `[]`; Task 2 `gather_context` returns `("", [])`. ✓
- `SEARCH_PROMPT` reworded to synthesize from results; `SEARCH_QUERY_TEMPLATES`, `EXCLUDE_DOMAINS` added → Task 2 Step 1. ✓
- `tavily-python` dependency, `TAVILY_API_KEY` env → Task 1 Step 5. ✓
- Grounding call removed → Task 2 Step 4 (rewrite replaces the grounded call). ✓
- Tests: `test_web_search.py`, `test_research.py`; `test_pipeline.py` untouched → Tasks 1 & 2. ✓
- Graceful degradation everywhere → covered by both tasks' tests. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every test step shows the actual asserts; commands have expected output. ✓

**3. Type consistency:** `search(query, max_results=5, exclude_domains=None) -> list[{title, uri, content}]` defined in Task 1 and consumed identically in Task 2. `gather_context(company) -> (text, sources)` with `sources = [{title, uri}]` consistent across the rewrite and its tests. Config names `SEARCH_QUERY_TEMPLATES`, `EXCLUDE_DOMAINS`, `SEARCH_PROMPT` match between `config.py` additions and `research.py` imports. ✓

## Out of Scope (from spec, do NOT build)

Region-aware source inclusion lists, full page-body fetching beyond Tavily's `content`, a configurable provider switch, and keeping Gemini grounding as a fallback.
