"""Everything that talks to Google: deep research and LLM extraction calls.

Pure report-dict logic lives in `financials.py`; the data contracts live in
`schemas.py`. This module is only the API boundary to Google's models.
"""

from pydantic import BaseModel

from google.genai import types

from config import (
    EXTRACT_PROMPT,
    NARRATIVE_PROMPT,
    RESEARCH_PROMPT,
    REVENUE_PROMPT,
)
from financials import _drop_forecast_years, _empty_report
from model import MODEL, RESEARCH_AGENT, client
from schemas import FinancialReport, NarrativeReport


def start_research(company: str) -> str:
    """Start a background deep-research interaction; returns its id."""
    interaction = client.interactions.create(
        agent=RESEARCH_AGENT,
        input=RESEARCH_PROMPT.format(company=company),
        background=True,
    )
    return interaction.id


def check_research(interaction_id: str) -> tuple[str, str]:
    """Poll one interaction. Returns (status, research_text).

    research_text is empty unless status is "completed".
    """
    interaction = client.interactions.get(interaction_id)
    if interaction.status == "completed":
        return "completed", interaction.output_text or ""
    return interaction.status, ""


def extract_narrative(research_text: str) -> dict:
    """One LLM call: research text -> the qualitative narrative fields only
    (summary, verdict, health, segments, highlights, risks). The numeric
    financials are sourced from the data layer, so this does not extract them.
    """
    response = client.models.generate_content(
        model=MODEL,
        contents=NARRATIVE_PROMPT + research_text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=NarrativeReport,
        ),
    )
    parsed = response.parsed
    if not isinstance(parsed, NarrativeReport):
        return {"summary": "", "verdict": "", "health": "mixed",
                "currency_unit": "", "segments": [], "highlights": [], "risks": []}
    return parsed.model_dump()


def extract_financials(research_text: str) -> dict:
    """One Gemini call: research text -> the full structured report (numbers +
    narrative). Used on the fallback path when the data source has no coverage.

    Schema-enforced, so the model cannot return a malformed shape.
    """
    response = client.models.generate_content(
        model=MODEL,
        contents=EXTRACT_PROMPT + research_text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FinancialReport,
        ),
    )
    parsed = response.parsed
    if not isinstance(parsed, FinancialReport):
        return _empty_report()
    result = parsed.model_dump()
    # Drop forecast/plan years so the trend and the latest-year KPI reflect
    # actual reported results only (and so the completeness gate can't be
    # satisfied by a forecast row masking a missing actual figure).
    result["financials"] = _drop_forecast_years(result.get("financials") or [])
    return result


class _RevenueYear(BaseModel):
    year: str
    revenue: float | None = None


class _RevenueExtract(BaseModel):
    financials: list[_RevenueYear]


def reextract_field(research_text: str, field: str, years: list[str]) -> dict:
    """Targeted second-pass extraction for one critical field the first pass
    missed. Currently only "revenue" is supported. `years` are the fiscal
    years the main extraction already found — the pass is anchored to them so
    it can't shift a figure to the wrong year or invent phantom years. Returns
    a partial dict (same shape as `extract_financials`) for `merge_extraction`;
    an empty dict if nothing was found or the field is unsupported.
    """
    if field != "revenue":
        return {}
    years = [y for y in (years or []) if y]
    if years:
        years_line = (
            "these fiscal years: " + ", ".join(years) + ". Return exactly one "
            "object per listed year and do NOT add any other year."
        )
    else:
        years_line = (
            "every fiscal year for which ACTUAL reported total revenue is "
            "stated in the text."
        )
    response = client.models.generate_content(
        model=MODEL,
        contents=REVENUE_PROMPT.format(years_line=years_line) + research_text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_RevenueExtract,
        ),
    )
    parsed = response.parsed
    if not isinstance(parsed, _RevenueExtract):
        return {}
    rows = _drop_forecast_years([r.model_dump() for r in parsed.financials])
    return {"financials": rows}
