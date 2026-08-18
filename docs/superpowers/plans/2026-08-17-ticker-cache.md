# Ticker Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remember resolved tickers on disk so a repeat report costs 3 model requests instead of 5.

**Architecture:** Two layers, each independently working. Task 1 adds `finreport/tools/ticker_cache.py` (a hand-editable JSON store) and has `resolve_ticker` consult it — removing the LLM call inside the tool. Task 2 has `run_agent` check the same cache before building its prompt and, on a hit, tell the agent the ticker — removing the agent's turn that would have called the tool at all.

**Tech Stack:** Python 3, stdlib `json`/`os` (atomic writes, same pattern as `JobStore`), the project's plain-assert test files.

## Global Constraints

- **Requests, not tokens, are the constraint.** The point of this feature is removing model *requests*; do not add any new one.
- **`resolve_ticker(company_name: str) -> str | None`** keeps its signature — `loop._dispatch` wraps it as `{"ticker": resolve_ticker(...)}`.
- **A broken cache must never break a report.** Every read failure (missing, empty, corrupt, malformed entry) degrades to a miss; every write failure is swallowed.
- **Never overwrite a usable existing entry** — a hand-correction must survive later resolves.
- **Cache keys are `company_name.strip().lower()`**; `"cmc"` and `"cmc vietnam"` are deliberately separate entries.
- **Tests are plain-assert files in `tests/`.** Run one with `./.venv/bin/python -m tests.test_<name>`, the suite with `./.venv/bin/python -m tests` → `All test modules passed.`
- **Use the venv:** `./.venv/bin/python`, never bare `python`.
- **Every commit message ends with:** `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Work from the project root: `Financial_report_agent/`.

---

### Task 1: The cache, and `resolve_ticker` uses it

**Files:**
- Create: `finreport/tools/ticker_cache.py`
- Create: `tests/test_ticker_cache.py`
- Modify: `finreport/tools/market_data.py` (imports, `TICKER_PROMPT`, `_Ticker`, `resolve_ticker`)
- Modify: `tests/test_market_data.py` (add three tests)
- Modify: `.gitignore`

**Interfaces:**
- Produces: `finreport.tools.ticker_cache.get(company_name: str) -> dict | None` returning `{"ticker": str, "name": str}`; `finreport.tools.ticker_cache.put(company_name: str, ticker: str, name: str = "") -> None`; module global `CACHE_FILE` (tests repoint it). `resolve_ticker` keeps `(company_name: str) -> str | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ticker_cache.py`:

```python
"""Tests for ticker_cache — the on-disk memory of resolved tickers.
Run: python -m tests.test_ticker_cache

Plain asserts, no framework. Every test repoints CACHE_FILE at a throwaway temp
file, so the real tickers.json is never touched.
"""

import json
import os
import tempfile

from finreport.tools import ticker_cache


def _use_temp_cache(contents=None):
    """Point the cache at a fresh temp file; optionally seed it."""
    path = os.path.join(tempfile.mkdtemp(), "tickers.json")
    if contents is not None:
        with open(path, "w") as fh:
            fh.write(contents if isinstance(contents, str) else json.dumps(contents))
    ticker_cache.CACHE_FILE = path
    return path


def test_put_then_get_round_trip():
    _use_temp_cache()
    ticker_cache.put("Vinamilk", "VNM.VN", "Vietnam Dairy Products JSC")
    assert ticker_cache.get("Vinamilk") == {
        "ticker": "VNM.VN", "name": "Vietnam Dairy Products JSC"}


def test_keys_ignore_case_and_whitespace():
    _use_temp_cache()
    ticker_cache.put("Vinamilk", "VNM.VN", "Vietnam Dairy")
    assert ticker_cache.get("  vinamilk  ")["ticker"] == "VNM.VN"
    assert ticker_cache.get("VINAMILK")["ticker"] == "VNM.VN"


def test_miss_returns_none():
    _use_temp_cache()
    assert ticker_cache.get("Nobody Inc") is None


def test_hand_written_bare_string_is_accepted():
    # The file is meant to be corrected by hand, where a plain string is natural.
    _use_temp_cache({"cmc": "CMG.VN"})
    assert ticker_cache.get("CMC") == {"ticker": "CMG.VN", "name": ""}


def test_existing_entry_is_not_overwritten():
    # A hand-correction must survive a later resolve of the same name.
    _use_temp_cache({"cmc": "CMG.VN"})
    ticker_cache.put("CMC", "CMC", "Commercial Metals Company")
    assert ticker_cache.get("CMC")["ticker"] == "CMG.VN"


def test_corrupt_file_reads_as_a_miss():
    _use_temp_cache("{not json at all")
    assert ticker_cache.get("Vinamilk") is None


def test_malformed_entry_is_replaced_by_a_good_one():
    _use_temp_cache({"vinamilk": {"ticker": None}})
    assert ticker_cache.get("Vinamilk") is None          # unusable -> a miss
    ticker_cache.put("Vinamilk", "VNM.VN", "Vietnam Dairy")
    assert ticker_cache.get("Vinamilk")["ticker"] == "VNM.VN"


def test_short_and_qualified_names_are_separate_entries():
    # A bad "cmc" entry must not poison "cmc vietnam".
    _use_temp_cache()
    ticker_cache.put("CMC", "CMC", "Commercial Metals Company")
    ticker_cache.put("CMC Vietnam", "CMG.VN", "CMC Corporation")
    assert ticker_cache.get("CMC")["ticker"] == "CMC"
    assert ticker_cache.get("CMC Vietnam")["ticker"] == "CMG.VN"


def test_empty_ticker_is_not_stored():
    _use_temp_cache()
    ticker_cache.put("Nowhere Inc", "", "")
    assert ticker_cache.get("Nowhere Inc") is None


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

Run: `./.venv/bin/python -m tests.test_ticker_cache`
Expected: FAIL — `ModuleNotFoundError: No module named 'finreport.tools.ticker_cache'`.

- [ ] **Step 3: Write the cache module**

Create `finreport/tools/ticker_cache.py`:

```python
"""Remember resolved tickers on disk, so a company is looked up only once.

resolve_ticker costs an LLM call, and requests — not tokens — are the binding
quota. The cache is a plain JSON file, meant to be readable and correctable by
hand:

    {"vinamilk": {"ticker": "VNM.VN", "name": "Vietnam Dairy Products JSC"}}

The company name is stored alongside the ticker so a wrong entry is obvious to a
human reading the file, and checkable by the agent at runtime.

Every failure degrades to a miss: a broken cache must never break a report.
"""

import json
import logging
import os

from finreport import ROOT

log = logging.getLogger(__name__)

CACHE_FILE = os.path.join(ROOT, "tickers.json")


def _key(company_name: str) -> str:
    """Cache key: case- and whitespace-insensitive. "cmc" and "cmc vietnam"
    stay distinct, so a bad short-name entry cannot poison a qualified one."""
    return (company_name or "").strip().lower()


def _load() -> dict:
    """The whole cache; {} when missing, empty, unreadable or not an object."""
    try:
        with open(CACHE_FILE) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get(company_name: str) -> dict | None:
    """{"ticker": ..., "name": ...} for a remembered company, else None.

    Tolerates a hand-written bare string ({"cmc": "CMG.VN"}), since that is what
    someone correcting the file by hand will naturally write.
    """
    entry = _load().get(_key(company_name))
    if isinstance(entry, str) and entry.strip():
        return {"ticker": entry.strip(), "name": ""}
    if isinstance(entry, dict):
        ticker = entry.get("ticker")
        if isinstance(ticker, str) and ticker.strip():
            return {"ticker": ticker.strip(), "name": str(entry.get("name") or "")}
    return None


def put(company_name: str, ticker: str, name: str = "") -> None:
    """Remember a resolve.

    A usable existing entry is never overwritten, so a hand-correction survives.
    An unusable one (malformed, empty ticker) is replaced. Write failures are
    swallowed — the cache may only ever save work, never block a report.
    """
    key = _key(company_name)
    if not key or not (ticker or "").strip():
        return
    if get(company_name):
        return
    cache = _load()
    cache[key] = {"ticker": ticker.strip(), "name": (name or "").strip()}
    try:
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(cache, fh, indent=2, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, CACHE_FILE)
    except OSError as e:
        log.warning("could not write the ticker cache: %s", e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m tests.test_ticker_cache`
Expected: PASS — `9/9 passed`.

- [ ] **Step 5: Write the failing tests for `resolve_ticker`**

Append to `tests/test_market_data.py` (before its `if __name__ == "__main__":` block). Note it currently imports only `_adapt`; add the two imports it needs at the top of the file:

```python
from finreport.tools import market_data, ticker_cache
from finreport.tools.market_data import _Ticker
```

The tests:

```python
# --- resolve_ticker + the on-disk cache ---

def test_cache_hit_skips_the_model_call():
    # The whole point of the feature: a remembered ticker costs no request.
    class _Models:
        def generate_content(self, **kwargs):
            raise AssertionError("the model must not be called on a cache hit")

    class _Client:
        models = _Models()

    saved = (market_data.client, ticker_cache.get)
    market_data.client = _Client()
    ticker_cache.get = lambda name: {"ticker": "VNM.VN", "name": "Vinamilk JSC"}
    try:
        assert market_data.resolve_ticker("Vinamilk") == "VNM.VN"
    finally:
        (market_data.client, ticker_cache.get) = saved


def test_miss_calls_the_model_and_remembers_the_result():
    written = {}

    class _Resp:
        parsed = _Ticker(ticker="VNM.VN", name="Vietnam Dairy Products JSC")

    class _Models:
        def generate_content(self, **kwargs):
            return _Resp()

    class _Client:
        models = _Models()

    saved = (market_data.client, ticker_cache.get, ticker_cache.put)
    market_data.client = _Client()
    ticker_cache.get = lambda name: None
    ticker_cache.put = lambda name, ticker, company="": written.update(
        {"key": name, "ticker": ticker, "company": company})
    try:
        assert market_data.resolve_ticker("Vinamilk") == "VNM.VN"
    finally:
        (market_data.client, ticker_cache.get, ticker_cache.put) = saved
    assert written == {"key": "Vinamilk", "ticker": "VNM.VN",
                       "company": "Vietnam Dairy Products JSC"}


def test_failed_resolve_is_not_remembered():
    # Never memoize a failure — the next run should get a fresh attempt.
    written = {}

    class _Resp:
        parsed = _Ticker(ticker=None)

    class _Models:
        def generate_content(self, **kwargs):
            return _Resp()

    class _Client:
        models = _Models()

    saved = (market_data.client, ticker_cache.get, ticker_cache.put)
    market_data.client = _Client()
    ticker_cache.get = lambda name: None
    ticker_cache.put = lambda name, ticker, company="": written.update({"x": 1})
    try:
        assert market_data.resolve_ticker("Nowhere Inc") is None
    finally:
        (market_data.client, ticker_cache.get, ticker_cache.put) = saved
    assert written == {}
```

- [ ] **Step 6: Run to verify they fail**

Run: `./.venv/bin/python -m tests.test_market_data`
Expected: FAIL — `_Ticker` has no `name` field (`TypeError`/validation error), and the cache tests fail because `resolve_ticker` does not consult the cache yet.

- [ ] **Step 7: Update `market_data.py`**

Add to the imports at the top (keep the existing ones):

```python
import logging

from finreport.tools import ticker_cache

log = logging.getLogger(__name__)
```

Replace `TICKER_PROMPT` with (only the final sentence changes):

```python
TICKER_PROMPT = (
    'What is the Yahoo Finance ticker symbol for the company "{company}"? '
    "Vietnamese-listed companies use the .VN suffix (e.g. Vinamilk -> VNM.VN, "
    "Hoa Phat -> HPG.VN, Mobile World -> MWG.VN). US companies use their plain "
    "symbol (e.g. Apple -> AAPL). Also return the official name of the company "
    "that ticker belongs to, so a wrong match can be spotted. Return null for "
    "the ticker if you are not confident."
)
```

Replace `_Ticker` with:

```python
class _Ticker(BaseModel):
    ticker: str | None = None
    name: str | None = None   # official name of the company that ticker belongs to
```

Replace `resolve_ticker` with:

```python
def resolve_ticker(company_name: str) -> str | None:
    """Map a company name to its Yahoo Finance ticker, or None if unsure.

    A remembered name is answered from the on-disk cache, which costs no model
    request. A fresh resolve is remembered for next time; a failure is not.
    """
    cached = ticker_cache.get(company_name)
    if cached:
        log.info("ticker for %r from cache: %s (%s)",
                 company_name, cached["ticker"], cached["name"])
        return cached["ticker"]
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=TICKER_PROMPT.format(company=company_name),
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=_Ticker),
        )
        parsed = resp.parsed
        if isinstance(parsed, _Ticker) and parsed.ticker:
            ticker = parsed.ticker.strip()
            ticker_cache.put(company_name, ticker, (parsed.name or "").strip())
            return ticker
    except Exception:
        return None
    return None
```

- [ ] **Step 8: Run to verify they pass**

Run: `./.venv/bin/python -m tests.test_market_data`
Expected: PASS — all tests, including the three new ones.

- [ ] **Step 9: Git-ignore the cache file**

In `.gitignore`, under the `# Runtime state & generated output` section (which already lists `jobs.json`, `jobs.json.tmp`, `reports/`), add:

```
tickers.json
tickers.json.tmp
```

- [ ] **Step 10: Run the full suite**

Run: `./.venv/bin/python -m tests`
Expected: `All test modules passed.`

- [ ] **Step 11: Commit**

```bash
git add finreport/tools/ticker_cache.py finreport/tools/market_data.py tests/test_ticker_cache.py tests/test_market_data.py .gitignore
git commit -m "feat: remember resolved tickers on disk

resolve_ticker now answers from a hand-editable tickers.json when it can,
removing its LLM call on repeat companies. The resolved company name is stored
alongside the ticker so a wrong entry is visible. Failures are never cached and a
broken cache degrades to a miss.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Tell the agent the ticker, so it skips the tool

**Files:**
- Modify: `finreport/agent/prompts.py` (add `KNOWN_TICKER_NOTE`)
- Modify: `finreport/agent/loop.py` (imports, `run_agent` prompt building)
- Modify: `tests/test_loop.py` (add two tests)

**Interfaces:**
- Consumes: `finreport.tools.ticker_cache.get(company_name) -> dict | None` with keys `"ticker"` and `"name"` (Task 1).
- Produces: `finreport.agent.prompts.KNOWN_TICKER_NOTE` (a format string taking `ticker` and `name`); `run_agent(company)` unchanged in signature and return type.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_loop.py` (before its `if __name__ == "__main__":` block):

```python
# --- the known-ticker note (cache hit skips resolve_ticker entirely) ---

def _capture_prompt(seen):
    """A _model_turn stub that records the opening prompt, then submits."""
    def stub(contents):
        seen["prompt"] = contents[0].parts[0].text
        return None, [("submit_report", {"summary": "S", "verdict": "V",
                                         "health": "good", "analysis": "A"})]
    return stub


def test_prompt_gains_the_known_ticker_on_a_cache_hit():
    seen = {}
    saved = agent_loop.ticker_cache.get
    agent_loop.ticker_cache.get = lambda c: {"ticker": "VNM.VN",
                                             "name": "Vietnam Dairy Products JSC"}
    agent_loop._model_turn = _capture_prompt(seen)
    try:
        agent_loop.run_agent("Vinamilk")
    finally:
        agent_loop.ticker_cache.get = saved
    assert "VNM.VN" in seen["prompt"]
    assert "Vietnam Dairy Products JSC" in seen["prompt"]


def test_prompt_is_unchanged_on_a_cache_miss():
    from finreport.agent.prompts import AGENT_PROMPT
    seen = {}
    saved = agent_loop.ticker_cache.get
    agent_loop.ticker_cache.get = lambda c: None
    agent_loop._model_turn = _capture_prompt(seen)
    try:
        agent_loop.run_agent("Vinamilk")
    finally:
        agent_loop.ticker_cache.get = saved
    assert seen["prompt"] == AGENT_PROMPT.format(company="Vinamilk")
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/python -m tests.test_loop`
Expected: FAIL — `AttributeError: module 'finreport.agent.loop' has no attribute 'ticker_cache'`.

- [ ] **Step 3: Add the note to `prompts.py`**

Append to the end of `finreport/agent/prompts.py`:

```python
# Appended to AGENT_PROMPT only when the ticker is already cached, so the agent
# can skip resolve_ticker entirely (saving a whole turn). The company name is
# included so the agent can tell a stale/wrong cache entry from a correct one.
KNOWN_TICKER_NOTE = (
    '''

The Yahoo Finance ticker for this company is already known: {ticker} ({name}). \
Use it directly with fetch_financials — you do not need to call resolve_ticker. \
Only call resolve_ticker if "{name}" is clearly not the company you were asked \
about.'''
)
```

- [ ] **Step 4: Use it in `run_agent`**

In `finreport/agent/loop.py`, change the prompts import to include the note and add the cache import (keep every other import as-is):

```python
from finreport.agent.prompts import AGENT_PROMPT, EXCLUDE_DOMAINS, KNOWN_TICKER_NOTE
from finreport.tools import ticker_cache
```

Then replace the first statement of `run_agent` — currently:

```python
    contents = [types.Content(
        role="user",
        parts=[types.Part(text=AGENT_PROMPT.format(company=company))])]
```

with:

```python
    # A remembered ticker is handed to the agent up front, so it can go straight
    # to fetch_financials instead of spending a turn on resolve_ticker.
    prompt = AGENT_PROMPT.format(company=company)
    known = ticker_cache.get(company)
    if known:
        prompt += KNOWN_TICKER_NOTE.format(ticker=known["ticker"],
                                           name=known["name"] or company)
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
```

(`known["name"] or company` covers a hand-written bare-string entry, which has no
stored name.)

- [ ] **Step 5: Run to verify they pass**

Run: `./.venv/bin/python -m tests.test_loop`
Expected: PASS — all tests, including the two new ones.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/bin/python -m tests`
Expected: `All test modules passed.`

- [ ] **Step 7: Verify the end-to-end saving with no API calls**

Run:
```bash
./.venv/bin/python -c "
import tempfile, os
from finreport.tools import ticker_cache
from finreport.agent import loop
ticker_cache.CACHE_FILE = os.path.join(tempfile.mkdtemp(), 'tickers.json')
ticker_cache.put('Vinamilk', 'VNM.VN', 'Vietnam Dairy Products JSC')
seen = {}
def stub(contents):
    seen['prompt'] = contents[0].parts[0].text
    return None, [('submit_report', {'summary':'S','verdict':'V','health':'good','analysis':'A'})]
loop._model_turn = stub
loop.run_agent('Vinamilk')
print('note injected:', 'VNM.VN' in seen['prompt'])
print('resolve_ticker discouraged:', 'you do not need to call resolve_ticker' in seen['prompt'])
"
```
Expected: both lines print `True`.

- [ ] **Step 8: Commit**

```bash
git add finreport/agent/prompts.py finreport/agent/loop.py tests/test_loop.py
git commit -m "feat: hand the agent a cached ticker so it skips resolve_ticker

run_agent checks the ticker cache before building its prompt; on a hit it
appends KNOWN_TICKER_NOTE naming the ticker and the company it belongs to, so
the agent goes straight to fetch_financials. Together with the cache itself this
takes a repeat report from 5 model requests to 3. The note states the company
name so the agent can reject a stale entry and re-resolve.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- New `ticker_cache.py` with `get`/`put`, `CACHE_FILE` under `ROOT` → Task 1 Step 3. ✓
- Key = strip+lower; `"cmc"` vs `"cmc vietnam"` separate → Task 1 `_key`, tested. ✓
- Value `{"ticker", "name"}`; hand-written bare string tolerated → Task 1 `get`, tested. ✓
- Never overwrite a usable entry; malformed replaced → Task 1 `put`, both tested. ✓
- Reads tolerate missing/empty/corrupt; writes swallowed → Task 1 `_load`/`put`, corrupt case tested. ✓
- Atomic write (temp + `os.replace`) → Task 1 `put`. ✓
- `tickers.json` git-ignored → Task 1 Step 9. ✓
- `resolve_ticker` consults cache, logs on hit, keeps `str | None`, does not cache failure → Task 1 Step 7, all three tested. ✓
- `_Ticker` gains `name`; `TICKER_PROMPT` asks for it (no extra request) → Task 1 Step 7. ✓
- Layer 2: `run_agent` checks cache, appends `KNOWN_TICKER_NOTE`; miss → prompt byte-identical → Task 2 Steps 3–4, both tested. ✓
- Note includes the company name and the re-resolve condition → Task 2 Step 3. ✓

**2. Placeholder scan:** No TBD/TODO. Every code step shows complete code or the exact old→new text; every command states expected output. ✓

**3. Type consistency:** `ticker_cache.get() -> dict | None` with keys `"ticker"`/`"name"` is defined in Task 1 and consumed identically in Task 2 (`known["ticker"]`, `known["name"]`). `put(company_name, ticker, name="")` matches its call in `resolve_ticker` and the stub signatures in the tests. `KNOWN_TICKER_NOTE` takes exactly the `ticker` and `name` passed by `run_agent`. `CACHE_FILE` is the name the tests repoint. ✓

## Out of Scope (from the spec — do NOT build)

TTL/expiry; a cache-management CLI; caching financials or search results; refusing to cache ambiguous "ticker-like" names.
