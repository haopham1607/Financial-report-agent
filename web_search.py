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
