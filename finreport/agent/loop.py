"""A hand-built tool-calling agent loop that builds one company's report.

The model is given four tools and a goal (AGENT_PROMPT); it decides which to call
and in what order, and calls submit_report when done. Code owns two invariants:
the yfinance numbers are stamped in last (authoritative), and the returned dict is
the same shape the rest of the app already consumes.
"""

import logging
import time

from google.genai import types

from finreport.agent.model import MODEL, client
from finreport.agent.prompts import (AGENT_PROMPT, EXCLUDE_DOMAINS,
                                     KNOWN_TICKER_NOTE)
from finreport.tools import ticker_cache
from finreport.tools.market_data import fetch_financials, resolve_ticker
from finreport.tools.web_search import search

log = logging.getLogger(__name__)

# Turns the agent gets before it must finish. 8 was too tight: a search-happy
# run (e.g. Sabeco) spent every step on web_search and never submitted, leaving a
# report with numbers but no narrative.
MAX_STEPS = 12

# A single run bursts several model calls, which trips the free tier's ~5/minute
# limit; pausing and resuming beats discarding the steps already completed.
MAX_RETRIES = 3
RETRY_BASE_DELAY = 20  # seconds; grows 20s, 40s, 60s

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


# --- one model turn + tool dispatch ---------------------------------------

def _is_transient(error) -> bool:
    """True for a rate limit (429) or an overloaded service (503)."""
    s = str(error)
    return ("429" in s or "RESOURCE_EXHAUSTED" in s
            or "503" in s or "UNAVAILABLE" in s)


def _model_turn(contents):
    """Call the model once. Return (model_content, [(name, args_dict), ...]).

    One agent run makes several calls back-to-back, which trips the free tier's
    per-minute limit mid-loop. Rather than lose the steps already completed, a
    transient 429/503 is retried after a growing pause; anything else — or a
    still-failing call after MAX_RETRIES — is raised so the job loop leaves the
    job `running` to retry later.
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=MODEL, contents=contents,
                config=types.GenerateContentConfig(tools=_TOOLS))
            break
        except Exception as e:
            if attempt == MAX_RETRIES or not _is_transient(e):
                raise
            delay = RETRY_BASE_DELAY * (attempt + 1)
            log.info("transient error (%s); retrying in %ds", str(e)[:60], delay)
            time.sleep(delay)
    # Gracefully handle empty or missing candidates (safety-filtered responses, etc.)
    if not resp.candidates:
        return None, []
    content = resp.candidates[0].content
    if content is None:
        return None, []
    calls = []
    for part in (content.parts or []):
        fc = getattr(part, "function_call", None)
        if fc:
            calls.append((fc.name, dict(fc.args or {})))
    return content, calls


def _dispatch(name, args):
    """Run a non-terminal tool; return a JSON-serialisable dict result.

    Never raises — a failing tool (e.g. web_search when tavily-python is
    missing) degrades to an {"error": ...} result the model can react to,
    instead of killing the whole run.
    """
    try:
        if name == "resolve_ticker":
            return {"ticker": resolve_ticker(args.get("company_name", ""))}
        if name == "fetch_financials":
            return fetch_financials(args.get("ticker", "")) or {}
        if name == "web_search":
            return {"results": search(args.get("query", ""),
                                      exclude_domains=EXCLUDE_DOMAINS)}
        return {"error": f"unknown tool {name}"}
    except Exception as e:
        return {"error": str(e)[:200]}


# --- the loop -------------------------------------------------------------

def run_agent(company: str) -> dict:
    """Drive the tool-calling loop for one company; return the report dict."""
    # A remembered ticker is handed to the agent up front, so it can go straight
    # to fetch_financials instead of spending a turn on resolve_ticker.
    prompt = AGENT_PROMPT.format(company=company)
    known = ticker_cache.get(company)
    if known:
        prompt += KNOWN_TICKER_NOTE.format(ticker=known["ticker"],
                                           name=known["name"] or company)
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    numbers, sources, seen = {}, [], set()
    final = None
    # The loop is nondeterministic, so record what it actually did: how many
    # turns it took, which tools it called, and whether it finished properly.
    steps, tools = 0, {}

    for _ in range(MAX_STEPS):
        steps += 1
        content, calls = _model_turn(contents)
        if content is not None:
            contents.append(content)
        if not calls:
            contents.append(types.Content(role="user", parts=[types.Part(
                text="Call a tool, or submit_report when you have enough.")]))
            continue
        # One turn may contain several function calls. The API contract is a
        # SINGLE Content (role="user" — "tool" is not a valid role) carrying
        # one function_response part per call, not N separate contents.
        response_parts = []
        for name, args in calls:
            tools[name] = tools.get(name, 0) + 1
            if name == "submit_report":
                # Record and keep dispatching the rest of this turn's calls
                # (e.g. a fetch_financials alongside it) instead of skipping
                # them; the outer loop still stops once the turn is done.
                final = args
                continue
            result = _dispatch(name, args)
            if name == "fetch_financials":
                # The prompt invites re-resolving/re-fetching; a second,
                # failing fetch must not wipe out numbers already captured.
                if result:
                    numbers = result
            elif name == "web_search":
                for r in result.get("results", []):
                    uri = r.get("uri")
                    if uri and uri not in seen:
                        seen.add(uri)
                        sources.append({"title": r.get("title") or uri, "uri": uri})
            response_parts.append(
                types.Part.from_function_response(name=name, response=result))
        if response_parts:
            contents.append(types.Content(role="user", parts=response_parts))
        if final is not None:
            break

    trace = {"steps": steps, "tools": tools, "submitted": final is not None}
    log.info("agent [%s]: %d steps, tools=%s, submitted=%s",
             company, steps, tools, final is not None)
    return _assemble(final, numbers, sources, trace)


# --- _assemble coercion helpers --------------------------------------------
# The model's submit_report args are untrusted input: missing keys, wrong
# types, or an out-of-enum health would otherwise flow straight into
# report.write_report (e.g. "\n".join(...) over a None, sum(...) over a
# string revenue) and crash the whole batch job outside its try/except.

_VALID_HEALTH = {"good", "mixed", "weak"}


def _as_str(value) -> str:
    return "" if value is None else str(value)


def _as_str_list(value) -> list:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str)]


def _as_health(value) -> str:
    return value if value in _VALID_HEALTH else "mixed"


def _as_segments(value) -> list:
    if not isinstance(value, list):
        return []
    out = []
    for seg in value:
        if not isinstance(seg, dict) or "name" not in seg or "revenue" not in seg:
            continue
        revenue = seg["revenue"]
        if isinstance(revenue, bool) or not isinstance(revenue, (int, float)):
            continue
        out.append({"name": str(seg["name"]), "revenue": revenue})
    return out


def _assemble(final, numbers, sources, trace=None) -> dict:
    """Combine the agent's narrative with the authoritative numbers + sources.

    `trace` (steps / tools called / whether it submitted) is carried through so a
    run can be inspected after the fact.
    """
    report = {}
    if final:
        report["summary"] = _as_str(final.get("summary"))
        report["verdict"] = _as_str(final.get("verdict"))
        report["health"] = _as_health(final.get("health"))
        report["segments"] = _as_segments(final.get("segments"))
        report["segment_period"] = _as_str(final.get("segment_period"))
        report["highlights"] = _as_str_list(final.get("highlights"))
        report["risks"] = _as_str_list(final.get("risks"))
        report["context"] = _as_str(final.get("analysis"))
    else:  # hit MAX_STEPS without submitting — best-effort empty narrative
        report.update({"summary": "", "verdict": "", "health": "mixed",
                       "segments": [], "segment_period": "",
                       "highlights": [], "risks": [], "context": ""})
    report["sources"] = sources
    report["trace"] = trace or {"steps": 0, "tools": {}, "submitted": False}
    report.update(numbers)   # yfinance numbers stamped LAST — authoritative
    return report
