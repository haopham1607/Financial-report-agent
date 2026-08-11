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

from config import SEARCH_PROMPT, WRITER_PROMPT
from model import MODEL, client
from schemas import NarrativeReport


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
    """Grounded search: gather qualitative context in the fixed SEARCH_PROMPT
    format. Returns (context text, cited web sources [{title, uri}]).
    """
    response = client.models.generate_content(
        model=MODEL,
        contents=SEARCH_PROMPT.format(company=company),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    text = response.text or ""
    sources = []
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
        for c in chunks:
            web = getattr(c, "web", None)
            uri = getattr(web, "uri", None) if web else None
            if uri:
                sources.append({"title": getattr(web, "title", "") or uri, "uri": uri})
    except (AttributeError, IndexError, TypeError):
        pass
    return text, sources


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
