"""Pure logic over the report dict — no network, no LLM, no I/O.

Judging completeness, merging supplementary data, and filtering forecast
years. Kept dependency-free so it is trivially unit-testable and reusable.
"""

import re


def _empty_report() -> dict:
    """A fully-null report dict — the shape everything downstream expects."""
    return {
        "summary": "(Could not extract structured data.)",
        "verdict": "",
        "health": "mixed",
        "currency_unit": "",
        "financials": [],
        "margins": {"gross": None, "operating": None, "net": None},
        "segments": [],
        "balance_sheet": {"cash": None, "debt": None,
                          "debt_to_equity": None, "current_ratio": None},
        "cash_flow": {"operating": None, "free": None},
        "highlights": [],
        "risks": [],
    }


def has_usable_financials(data: dict) -> bool:
    """True if extraction produced at least one real figure worth rendering.

    We judge the *result* rather than the source format: a report is worth
    keeping if any headline number came through, and is dropped only when
    extraction found essentially nothing (an all-null / empty result).
    """
    for row in data.get("financials") or []:
        if row.get("revenue") is not None or row.get("net_income") is not None:
            return True
    if any(v is not None for v in (data.get("margins") or {}).values()):
        return True
    bs = data.get("balance_sheet") or {}
    if bs.get("cash") is not None or bs.get("debt") is not None:
        return True
    cf = data.get("cash_flow") or {}
    if cf.get("operating") is not None or cf.get("free") is not None:
        return True
    return False


# Year labels that denote a forecast / plan / target rather than actual
# reported results — these must not enter the financials the dashboard plots,
# and must not mask a missing actual latest-year figure in the gate below.
_FORECAST_MARKERS = (
    "kế hoạch", "dự báo", "dự kiến", "mục tiêu", "ước tính",
    "forecast", "plan", "target", "projected", "guidance", "outlook", "estimate",
)


def _is_forecast_year(year: str) -> bool:
    """True if a financials 'year' label denotes a forecast/plan, not actuals
    (e.g. "2026 (Kế hoạch)", "2026 (Dự báo)", "2026F", "2026E")."""
    y = (year or "").strip().lower()
    if any(marker in y for marker in _FORECAST_MARKERS):
        return True
    return bool(re.fullmatch(r"\d{4}\s*[fep]", y))


def _drop_forecast_years(financials: list) -> list:
    """Keep only actual reported years — forecast/plan rows belong in the
    narrative, not in the plotted figures."""
    return [r for r in financials if not _is_forecast_year(r.get("year", ""))]


def missing_critical_fields(data: dict) -> list[str]:
    """Which must-have figures are absent.

    The dashboard's headline is revenue for the most recent fiscal year; when
    it is absent we run a supplementary source (or flag the report incomplete)
    before deciding it is done.
    """
    missing = []
    financials = data.get("financials") or []
    latest = financials[-1] if financials else {}
    if latest.get("revenue") is None:
        missing.append("revenue")
    return missing


def merge_extraction(base: dict, patch: dict, add_years: bool = False) -> dict:
    """Fill only the null fields of `base` from `patch`; never overwrite a
    value the first pass already found. Folds a supplementary source back into
    the main result. Mutates and returns `base`.

    Patch rows enrich existing years (matched by "year"). Whether a patch year
    absent from `base` may be *added*:
    - `add_years=False` (default): only when `base` had no years at all — so an
      untrusted LLM re-extract can't invent phantom years on an established set.
    - `add_years=True`: always — for a trusted source (the yfinance data layer),
      whose years are real financial-statement years and should extend a thin
      series the LLM happened to under-populate.
    """
    base_fin = base.setdefault("financials", [])
    can_add = add_years or not base_fin  # trusted source, or nothing to anchor to
    by_year = {r.get("year"): r for r in base_fin}
    for row in patch.get("financials") or []:
        existing = by_year.get(row.get("year"))
        if existing is not None:
            for key, value in row.items():
                if key != "year" and existing.get(key) is None and value is not None:
                    existing[key] = value
        elif can_add and any(v is not None for k, v in row.items() if k != "year"):
            base_fin.append(dict(row))
            by_year[row.get("year")] = base_fin[-1]
    base_fin.sort(key=lambda r: r.get("year") or "")
    for section in ("margins", "balance_sheet", "cash_flow"):
        patch_sec = patch.get(section)
        if isinstance(patch_sec, dict):
            base_sec = base.setdefault(section, {})
            for key, value in patch_sec.items():
                if base_sec.get(key) is None and value is not None:
                    base_sec[key] = value
    return base
