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
