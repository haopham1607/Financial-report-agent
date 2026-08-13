"""Assemble a structured report from the data source + gathered context.

Given a company name: fetch its numbers from the data source, gather qualitative
context from a grounded web search (fixed format), then have the writer fuse the
two into the structured financial-health report — with the data source owning
every figure. Kept separate from job orchestration so it is testable/reusable.
"""

from data_source import fetch_financials, resolve_ticker
from research import gather_context, write_narrative


def build_report(company: str) -> dict:
    """Build the report dict for one company.

    Numbers come from the data source (authoritative). A grounded search gathers
    qualitative context (business, segments, developments, risks, ...). The
    writer combines the numbers and the context into the report; the context and
    its sources are carried through for display.
    """
    ticker = resolve_ticker(company)
    numbers = fetch_financials(ticker) if ticker else {}

    # Pass the resolved ticker so the web search targets the same company as the
    # numbers (an ambiguous name alone can pull in unrelated same-named firms).
    context, sources = gather_context(company, ticker or "")
    data = write_narrative(company, numbers, context)
    data.update(numbers)  # data source owns financials / margins / bs / cf / unit
    data["context"] = context
    data["sources"] = sources
    return data
