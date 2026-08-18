# Ticker Cache — Design

**Date:** 2026-08-17
**Status:** Approved, implementing

## Problem

Every report re-derives the same fact. `resolve_ticker("Vinamilk") → "VNM.VN"` is
a separate LLM call on every run, and the agent spends a whole turn asking for
it — so a company you have already built costs two model requests just to learn
something the project already knew.

That matters because **requests, not tokens, are the binding constraint.** The
free tier's ~20 requests/day is what has repeatedly blocked live runs; token
usage sits around 8% of its cap. A typical report costs 5 requests:

| Step | Requests |
|------|----------|
| Agent turn deciding to call `resolve_ticker` | 1 |
| The LLM call inside `resolve_ticker` | 1 |
| Agent turns for fetch / search / submit | 3 |

## Goal

Remember resolved tickers on disk and use them to remove **both** ticker-related
requests, taking a warm run from 5 requests to 3 — roughly 4 → 6 reports per day
on the free tier.

## Design

Two layers. The first works on its own; the second is a small increment on top
and is independently revertible.

### Layer 1 — the cache, inside the tool

**New module `finreport/tools/ticker_cache.py`**, following the `JobStore`
pattern (JSON + atomic writes) so persistence stays out of `market_data.py`:

```python
CACHE_FILE = os.path.join(ROOT, "tickers.json")

def get(company_name: str) -> dict | None
    """{"ticker": "VNM.VN", "name": "Vietnam Dairy Products JSC"} or None."""

def put(company_name: str, ticker: str, name: str = "") -> None
    """Remember a resolve. Never overwrites an existing entry."""
```

- **Key:** `company_name.strip().lower()` — `"Vinamilk"`, `"vinamilk"` and
  `" VINAMILK "` share one entry. `"cmc"` and `"cmc vietnam"` are deliberately
  *separate* entries, so a bad short-name entry cannot poison a qualified one.
- **Value:** `{"ticker": ..., "name": ...}` where `name` is the official company
  name the resolve identified.
- **Hand-edited bare strings are tolerated.** The file is meant to be corrected
  by hand, and a human will naturally write `"cmc": "CMG.VN"`. `get()` accepts
  both shapes, normalising a bare string to `{"ticker": "CMG.VN", "name": ""}`.
- **Never overwrites** an existing key, so a hand-correction is permanent.
- **Reads tolerate anything** — missing file, empty file, corrupt JSON, wrong
  types → `None`. A broken cache degrades to "no cache"; it must never break a
  report.
- **Writes are atomic** (temp file + `os.replace`), like `jobs.json`, and a write
  failure is swallowed — the cache may only ever save work, never block it.
- `tickers.json` is git-ignored, like `jobs.json` (local runtime state).

**`resolve_ticker` in `finreport/tools/market_data.py`** gains a cache check and
a write, and nothing else changes:

```python
def resolve_ticker(company_name: str) -> str | None:
    cached = ticker_cache.get(company_name)
    if cached:
        log.info("ticker for %r from cache: %s (%s)",
                 company_name, cached["ticker"], cached["name"])
        return cached["ticker"]
    <existing LLM call, producing `parsed`>
    if parsed.ticker:
        ticker_cache.put(company_name, parsed.ticker.strip(), parsed.name or "")
    return parsed.ticker.strip()
```

(`parsed.name` is the new schema field below; it is `""` when the model omits it,
which the cache stores as an empty name rather than failing.)

The **public contract is unchanged** — it still returns `str | None`, because
`loop._dispatch` wraps it as `{"ticker": resolve_ticker(...)}` and the tool
schema expects a ticker. A failed resolve (`None`) is **not** cached; we do not
memoize failure.

**Getting the company name costs nothing extra.** The existing `_Ticker` response
schema gains a field and `TICKER_PROMPT` asks for the official company name
alongside the symbol — the same single call returns both:

```python
class _Ticker(BaseModel):
    ticker: str | None = None
    name: str | None = None      # official company name, for the cache
```

### Layer 2 — pre-injection, in the loop

`run_agent` checks the cache before building the prompt. On a hit it appends one
sentence, so the agent skips the `resolve_ticker` tool entirely:

```python
def run_agent(company: str) -> dict:
    prompt = AGENT_PROMPT.format(company=company)
    known = ticker_cache.get(company)
    if known:
        prompt += KNOWN_TICKER_NOTE.format(
            ticker=known["ticker"], name=known["name"])
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    ...
```

**New `KNOWN_TICKER_NOTE` in `finreport/agent/prompts.py`:**

> The Yahoo Finance ticker for this company is already known: `{ticker}`
> (`{name}`). Use it directly with `fetch_financials` — you do not need
> `resolve_ticker`. Only call `resolve_ticker` if `{name}` is clearly not the
> company you were asked about.

The note is appended **only on a cache hit**, so a cold run's prompt is
byte-identical to today's.

### Why storing the name matters more than readability

It was proposed to make a wrong entry obvious when opening the file, and it does
that. But in Layer 2 it also becomes a **correctness mechanism**: the agent is
shown `CMC (Commercial Metals Company)` while being asked about a Vietnamese
company, and the note explicitly licenses it to re-resolve when the name does not
match. Without the name, the agent would see a bare symbol with no way to judge
it.

This is the main mitigation for the design's known risk: a cache freezes the
first answer, trading "occasionally wrong at random" for "consistently wrong
until corrected". The other two mitigations are the cache-hit log line and the
hand-editable file.

## Error handling

Every failure degrades to today's behavior:

| Failure | Result |
|---------|--------|
| `tickers.json` missing / empty / corrupt | treated as a miss → normal LLM resolve |
| Entry present but malformed (not a str/dict, no ticker) | treated as a miss |
| Cache write fails (disk, permissions) | swallowed; the report still builds |
| Cached ticker is wrong | agent may re-resolve (Layer 2 note); human edits one line |

## Testing

**`tests/test_ticker_cache.py` (new)** — against a temp file, no network:
round-trip `put`/`get`; keys are case- and whitespace-insensitive; a miss returns
`None`; a bare-string entry is normalised to a dict; an existing entry is not
overwritten; corrupt JSON returns `None` instead of raising; `"cmc"` and
`"cmc vietnam"` stay independent.

**`tests/test_market_data.py`** — add: a cache hit returns the ticker **without
calling the model** (stub the client and assert it was never invoked); a miss
calls the model and writes the entry; a `None` resolve writes nothing.

**`tests/test_loop.py`** — add: with a cache hit, the first prompt contains the
known ticker and its name; with a miss, the prompt is exactly
`AGENT_PROMPT.format(company=...)` (unchanged from today).

## What stays the same

The agent's tool set, the report shape, `build_report`'s contract, the job queue,
the dashboard, and `resolve_ticker`'s signature. A cold run behaves exactly as it
does today.

## Out of scope (YAGNI)

- TTL / expiry — tickers effectively do not change; staleness is handled by
  editing the file.
- A CLI to manage the cache — the file is the interface.
- Caching anything else (financials, search results) — different lifetimes and
  freshness requirements; revisit separately if ever needed.
- Refusing to cache "ticker-like" ambiguous names (e.g. bare `CMC`) — the name
  field plus the Layer 2 note already give the agent grounds to reject a
  mismatch.

## Risks

- **A frozen wrong answer.** Caching removes the nondeterminism that could
  accidentally self-correct. Mitigated by the stored name (agent can spot the
  mismatch), the log line, and the editable file.
- **The agent trusting the injected ticker.** It is told rather than deriving it.
  Mitigated by the note's explicit condition for re-resolving.
