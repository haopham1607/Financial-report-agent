"""The Google model calls: gather qualitative context, then write the report.

Two distinct stages:
  1. gather_context — a Google-Search-grounded call that gathers qualitative
     information in a fixed format (business, segments, developments, outlook,
     competitive position, risks) plus cited sources. It only finds information.
  2. write_narrative — a plain, schema-enforced call that fuses the ACTUAL
     numbers (from the yfinance data layer) with that context into the
     structured financial-health report.

They are separate because grounding cannot be combined with a response schema:
stage 1 is grounded free text, stage 2 is schema-enforced with no tools.
"""

from google.genai import types

from config import SEARCH_PROMPT, WRITER_PROMPT, SEARCH_QUERY_TEMPLATES, EXCLUDE_DOMAINS
from model import MODEL, client
from schemas import NarrativeReport
from web_search import search


def _format_figures(numbers: dict) -> str:
    """Render the yfinance numbers as a compact block for the writer prompt."""
    unit = numbers.get("currency_unit", "") or ""
    lines = []
    for r in numbers.get("financials") or []:
        lines.append(
            f"  {r.get('year')}: revenue={r.get('revenue')} "
            f"net_income={r.get('net_income')} ({unit})")
    m = numbers.get("margins") or {}
    lines.append(
        f"  margins: gross={m.get('gross')}% operating={m.get('operating')}% "
        f"net={m.get('net')}%")
    bs = numbers.get("balance_sheet") or {}
    lines.append(
        f"  balance sheet: cash={bs.get('cash')} debt={bs.get('debt')} "
        f"debt/equity={bs.get('debt_to_equity')}% "
        f"current_ratio={bs.get('current_ratio')} ({unit})")
    cf = numbers.get("cash_flow") or {}
    lines.append(
        f"  cash flow: operating={cf.get('operating')} free={cf.get('free')} ({unit})")
    return "\n".join(lines) if lines else "  (no figures available)"


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


def write_narrative(company: str, numbers: dict, context: str) -> dict:
    """Writer: fuse the ACTUAL numbers with the gathered context into the
    structured report fields (summary, verdict, health, segments, highlights,
    risks). Schema-enforced, no tools. Returns a plain dict.
    """
    prompt = WRITER_PROMPT.format(
        company=company, figures=_format_figures(numbers)) + context
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=NarrativeReport,
        ),
    )
    parsed = response.parsed
    if not isinstance(parsed, NarrativeReport):
        return {"summary": "", "verdict": "", "health": "mixed",
                "currency_unit": "", "segments": [], "segment_period": "",
                "highlights": [], "risks": []}
    return parsed.model_dump()
