"""Shared data contracts — the structured shape of a financial report.

These Pydantic models are the schema the LLM extraction is enforced against
and the shape the dashboard renders. One home so every module agrees on it.
"""

from typing import Literal

from pydantic import BaseModel


class YearFinancial(BaseModel):
    year: str
    revenue: float | None = None
    net_income: float | None = None


class Margins(BaseModel):
    gross: float | None = None
    operating: float | None = None
    net: float | None = None


class Segment(BaseModel):
    name: str
    revenue: float | None = None


class BalanceSheet(BaseModel):
    cash: float | None = None  # cash + short-term investments, in currency_unit
    debt: float | None = None  # total financial debt, in currency_unit
    debt_to_equity: float | None = None  # percent, e.g. 40 for 40%
    current_ratio: float | None = None  # times, e.g. 1.4


class CashFlow(BaseModel):
    operating: float | None = None  # operating cash flow, in currency_unit
    free: float | None = None  # free cash flow, in currency_unit


class FinancialReport(BaseModel):
    """The full report — numbers + narrative (used by the LLM fallback path)."""
    summary: str
    verdict: str  # one-line plain-language health statement
    health: Literal["good", "mixed", "weak"]
    currency_unit: str
    financials: list[YearFinancial]
    margins: Margins
    segments: list[Segment]
    balance_sheet: BalanceSheet
    cash_flow: CashFlow
    highlights: list[str]
    risks: list[str]


class NarrativeReport(BaseModel):
    """The qualitative half of a report — numbers come from the data layer."""
    summary: str
    verdict: str
    health: Literal["good", "mixed", "weak"]
    currency_unit: str
    segments: list[Segment]
    # Period the segment figures cover, e.g. "Cả năm 2025" or "6 tháng đầu năm
    # 2026". Any timeframe is allowed, but it must be stated (shown on the chart)
    # so an interim breakdown is never mistaken for a full-year one. "" if no segments.
    segment_period: str = ""
    highlights: list[str]
    risks: list[str]
