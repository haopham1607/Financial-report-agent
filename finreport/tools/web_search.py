"""Web search via Tavily — the retrieval tool.

Isolates the provider behind one function so the rest of the app never imports
Tavily directly (swap the provider by changing only this file). Every failure
degrades to an empty list, so callers never need a try/except.
"""

import logging
import os

from dotenv import load_dotenv

from finreport import ROOT

# Load .env from this file's directory so the tool is self-contained: it works
# standalone (scripts, tests, any caller) regardless of whether model.py was
# imported first. load_dotenv does not override variables already in the env.
load_dotenv(os.path.join(ROOT, ".env"))

log = logging.getLogger(__name__)


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
        log.warning("TAVILY_API_KEY not set; web search returns no results")
        return []
    try:
        resp = client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",
            exclude_domains=exclude_domains or [],
        )
    except Exception as e:
        # Degrade to empty, but leave a trace — otherwise a Tavily quota/auth
        # failure is indistinguishable from "genuinely no results" when a report
        # comes back with no context.
        log.warning("Tavily search failed for %r: %s", query, e)
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
