"""Assemble a structured report from the research + data sources.

This is the report-building brain, kept separate from job orchestration
(`agent.py`) so it can be tested and reused on its own. Given a company name
and its research text, it returns the report dict the dashboard renders.
"""

from data_source import fetch_financials, resolve_ticker
from financials import merge_extraction, missing_critical_fields
from research import extract_financials, extract_narrative, reextract_field


def build_report(company: str, research_text: str) -> dict:
    """Build the report dict for one company.

    yfinance-primary: numbers come from the structured data source (authoritative)
    and the narrative from the research. When the data source has no coverage for
    the company, fall back to extracting the numbers from the research prose (with
    the completeness gate).
    """
    ticker = resolve_ticker(company)
    numbers = fetch_financials(ticker) if ticker else {}

    if numbers:
        data = extract_narrative(research_text)
        data.update(numbers)  # yfinance owns financials / margins / bs / cf / unit
        return data

    # Fallback: no structured data for this company — extract numbers from prose.
    data = extract_financials(research_text)
    for field in missing_critical_fields(data):
        years = [r.get("year") for r in data.get("financials") or []]
        data = merge_extraction(data, reextract_field(research_text, field, years))
    return data
