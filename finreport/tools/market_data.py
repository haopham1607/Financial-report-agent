"""Structured financial data from yfinance — a deterministic fill layer.

When the LLM pipeline leaves a critical figure missing, we fetch it from
Yahoo Finance instead of guessing. Numbers are mapped and normalised in plain
code (no LLM); the only LLM step is resolving a company name to a ticker.
"""

import logging

import yfinance as yf
from google.genai import types
from pydantic import BaseModel

from finreport.agent.model import MODEL, client
from finreport.tools import ticker_cache

log = logging.getLogger(__name__)

# --- name -> ticker (the one small LLM call) ------------------------------

TICKER_PROMPT = (
    'What is the Yahoo Finance ticker symbol for the company "{company}"? '
    "Vietnamese-listed companies use the .VN suffix (e.g. Vinamilk -> VNM.VN, "
    "Hoa Phat -> HPG.VN, Mobile World -> MWG.VN). US companies use their plain "
    "symbol (e.g. Apple -> AAPL). Also return the official name of the company "
    "that ticker belongs to, so a wrong match can be spotted. Return null for "
    "the ticker if you are not confident."
)


class _Ticker(BaseModel):
    ticker: str | None = None
    name: str | None = None   # official name of the company that ticker belongs to


def resolve_ticker(company_name: str) -> str | None:
    """Map a company name to its Yahoo Finance ticker, or None if unsure.

    A remembered name is answered from the on-disk cache, which costs no model
    request. A fresh resolve is remembered for next time; a failure is not.
    """
    cached = ticker_cache.get(company_name)
    if cached:
        log.info("ticker for %r from cache: %s (%s)",
                 company_name, cached["ticker"], cached["name"])
        return cached["ticker"]
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=TICKER_PROMPT.format(company=company_name),
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=_Ticker),
        )
        parsed = resp.parsed
        if isinstance(parsed, _Ticker) and parsed.ticker:
            ticker = parsed.ticker.strip()
            ticker_cache.put(company_name, ticker, (parsed.name or "").strip())
            return ticker
    except Exception:
        return None
    return None


# --- yfinance -> our schema (pure code) -----------------------------------

# key -> (which statement, yfinance row label)
_YF_ROWS = {
    "revenue": ("income", "Total Revenue"),
    "gross_profit": ("income", "Gross Profit"),
    "operating_income": ("income", "Operating Income"),
    "net_income": ("income", "Net Income"),
    # "cash + short-term investments" (our schema); fall back to strict cash.
    "cash": ("balance", ("Cash Cash Equivalents And Short Term Investments",
                         "Cash And Cash Equivalents")),
    "total_debt": ("balance", "Total Debt"),
    "equity": ("balance", "Stockholders Equity"),
    "current_assets": ("balance", "Current Assets"),
    "current_liabilities": ("balance", "Current Liabilities"),
    "op_cashflow": ("cashflow", "Operating Cash Flow"),
    "capex": ("cashflow", "Capital Expenditure"),
}

_CURRENCY_UNIT = {"VND": "tỷ VNĐ", "USD": "USD billion", "EUR": "EUR billion"}


def _b(value):
    """Raw currency -> billions, rounded; None passes through."""
    return round(value / 1e9, 1) if value is not None else None


def _row_values(df, name) -> dict:
    """{year: value} for a yfinance row, skipping NaN; {} if absent.

    `name` may be a single label or a tuple of candidate labels tried in order
    (first one present with data wins) — used e.g. for cash, which has a broad
    "…And Short Term Investments" variant and a strict one.
    """
    if df is None or getattr(df, "empty", True):
        return {}
    names = (name,) if isinstance(name, str) else tuple(name)
    for n in names:
        if n not in df.index:
            continue
        out = {}
        for col in df.columns:
            v = df.loc[n, col]
            if v == v:  # not NaN
                out[col.year] = float(v)
        if out:
            return out
    return {}


def _adapt(rows: dict, currency: str) -> dict:
    """Map/normalise/compute the fetched rows into a partial report dict.

    `rows` is {key: {year: raw_value}} in the native currency. Returns {} when
    there is no revenue (nothing worth filling).
    """
    revenue = rows.get("revenue") or {}
    if not revenue:
        return {}
    years = sorted(revenue)[-4:]  # up to 4 most recent, oldest first
    net_income = rows.get("net_income") or {}
    financials = [
        {"year": str(y), "revenue": _b(revenue.get(y)),
         "net_income": _b(net_income.get(y))}
        for y in years
    ]

    latest = years[-1]

    def margin(numer_key):
        n = (rows.get(numer_key) or {}).get(latest)
        r = revenue.get(latest)
        return round(n / r * 100, 1) if (n is not None and r) else None

    debt = (rows.get("total_debt") or {}).get(latest)
    equity = (rows.get("equity") or {}).get(latest)
    cur_assets = (rows.get("current_assets") or {}).get(latest)
    cur_liab = (rows.get("current_liabilities") or {}).get(latest)
    op_cf = (rows.get("op_cashflow") or {}).get(latest)
    capex = (rows.get("capex") or {}).get(latest)  # negative in yfinance

    if currency in _CURRENCY_UNIT:
        unit = _CURRENCY_UNIT[currency]
    elif currency:
        unit = f"{currency} billion"
    else:
        unit = "billion"

    return {
        "currency_unit": unit,
        "financials": financials,
        "margins": {
            "gross": margin("gross_profit"),
            "operating": margin("operating_income"),
            "net": margin("net_income"),
        },
        "balance_sheet": {
            "cash": _b((rows.get("cash") or {}).get(latest)),
            "debt": _b(debt),
            "debt_to_equity": (round(debt / equity * 100, 1)
                               if (debt is not None and equity) else None),
            "current_ratio": (round(cur_assets / cur_liab, 2)
                              if (cur_assets is not None and cur_liab) else None),
        },
        "cash_flow": {
            "operating": _b(op_cf),
            "free": (_b(op_cf + capex)
                     if (op_cf is not None and capex is not None) else None),
        },
    }


def fetch_financials(ticker: str) -> dict:
    """Fetch financials for a ticker and adapt to our schema; {} on any failure."""
    try:
        t = yf.Ticker(ticker)
        frames = {
            "income": t.income_stmt,
            "balance": t.balance_sheet,
            "cashflow": t.cashflow,
        }
        rows = {
            key: _row_values(frames[which], name)
            for key, (which, name) in _YF_ROWS.items()
        }
        currency = ""
        try:
            info = t.info or {}
            currency = info.get("financialCurrency") or info.get("currency") or ""
        except Exception:
            currency = ""
        if not currency:
            currency = "VND" if ticker.upper().endswith(".VN") else ""
        return _adapt(rows, currency)
    except Exception:
        return {}
