"""Lightweight tests for research-result validation. Run: python test_research.py

Plain asserts, no test framework — this project keeps its dependencies to
the three in requirements.txt.
"""

from financials import (
    _drop_forecast_years,
    _empty_report,
    _is_forecast_year,
    has_usable_financials,
    merge_extraction,
    missing_critical_fields,
)


def test_empty_extraction_is_not_usable():
    # The failure mode this guard exists for: extraction found nothing.
    assert has_usable_financials(_empty_report()) is False


def test_revenue_makes_it_usable():
    data = _empty_report()
    data["financials"] = [{"year": "2024", "revenue": 100.0, "net_income": None}]
    assert has_usable_financials(data) is True


def test_net_income_alone_makes_it_usable():
    # A prose-only report often yields profit but not the revenue series.
    data = _empty_report()
    data["financials"] = [{"year": "2025", "revenue": None, "net_income": 11232.0}]
    assert has_usable_financials(data) is True


def test_margins_alone_make_it_usable():
    data = _empty_report()
    data["margins"] = {"gross": None, "operating": None, "net": 16.0}
    assert has_usable_financials(data) is True


def test_balance_sheet_alone_makes_it_usable():
    data = _empty_report()
    data["balance_sheet"] = {"cash": 40153.0, "debt": None,
                             "debt_to_equity": None, "current_ratio": None}
    assert has_usable_financials(data) is True


def test_cash_flow_alone_makes_it_usable():
    data = _empty_report()
    data["cash_flow"] = {"operating": 10136.0, "free": None}
    assert has_usable_financials(data) is True


def test_all_null_financials_is_not_usable():
    # Years extracted but every figure null — nothing to render.
    data = _empty_report()
    data["financials"] = [
        {"year": "2023", "revenue": None, "net_income": None},
        {"year": "2024", "revenue": None, "net_income": None},
    ]
    assert has_usable_financials(data) is False


# --- forecast years must be excluded from plotted figures ---

def test_actual_years_are_not_forecasts():
    for y in ("2024", "2025", "2023 (Actual)", "FY2025", ""):
        assert _is_forecast_year(y) is False, y


def test_plan_and_forecast_years_are_detected():
    for y in ("2026 (Kế hoạch)", "2027 (Dự báo)", "2026 (Dự kiến)",
              "2026F", "2026E", "2026 forecast", "2026 (target)"):
        assert _is_forecast_year(y) is True, y


def test_drop_forecast_years_keeps_only_actuals():
    financials = [
        {"year": "2024", "revenue": 62849.0, "net_income": 9427.0},
        {"year": "2025", "revenue": 70113.0, "net_income": 9376.0},
        {"year": "2026 (Kế hoạch)", "revenue": 80000.0, "net_income": None},
    ]
    kept = _drop_forecast_years(financials)
    assert [r["year"] for r in kept] == ["2024", "2025"]


def test_gate_not_fooled_by_forecast_latest_year():
    # After dropping the forecast row, the latest ACTUAL year (2025) has no
    # revenue, so the gate correctly reports revenue missing.
    data = _empty_report()
    data["financials"] = _drop_forecast_years([
        {"year": "2025", "revenue": None, "net_income": 9830.0},
        {"year": "2026 (Kế hoạch)", "revenue": 66450.0, "net_income": None},
    ])
    assert missing_critical_fields(data) == ["revenue"]


# --- missing_critical_fields: does the result have the must-have figures? ---

def test_missing_revenue_when_financials_empty():
    assert missing_critical_fields(_empty_report()) == ["revenue"]


def test_missing_revenue_when_latest_year_has_no_revenue():
    data = _empty_report()
    data["financials"] = [
        {"year": "2024", "revenue": 100.0, "net_income": 10.0},
        {"year": "2025", "revenue": None, "net_income": 11.0},
    ]
    assert missing_critical_fields(data) == ["revenue"]


def test_no_missing_when_latest_revenue_present():
    data = _empty_report()
    data["financials"] = [{"year": "2025", "revenue": 70000.0, "net_income": 11226.0}]
    assert missing_critical_fields(data) == []


# --- merge_extraction: fold a targeted re-extraction back in, nulls only ---

def test_merge_fills_null_revenue_by_year():
    base = _empty_report()
    base["financials"] = [
        {"year": "2024", "revenue": None, "net_income": None},
        {"year": "2025", "revenue": None, "net_income": 11226.0},
    ]
    patch = {"financials": [
        {"year": "2024", "revenue": 58580.0},
        {"year": "2025", "revenue": 70000.0},
    ]}
    out = merge_extraction(base, patch)
    by_year = {r["year"]: r for r in out["financials"]}
    assert by_year["2024"]["revenue"] == 58580.0
    assert by_year["2025"]["revenue"] == 70000.0
    assert by_year["2025"]["net_income"] == 11226.0  # first-pass value preserved


def test_merge_never_overwrites_existing_value():
    base = _empty_report()
    base["financials"] = [{"year": "2025", "revenue": 100.0, "net_income": None}]
    patch = {"financials": [{"year": "2025", "revenue": 999.0}]}
    out = merge_extraction(base, patch)
    assert out["financials"][0]["revenue"] == 100.0  # not overwritten


def test_merge_ignores_unknown_year_when_base_has_years():
    # A stray/mis-attributed year from the targeted pass must not pollute an
    # established year set — it's dropped, not appended.
    base = _empty_report()
    base["financials"] = [{"year": "2025", "revenue": None, "net_income": 11226.0}]
    patch = {"financials": [{"year": "2026", "revenue": 58580.0}]}
    out = merge_extraction(base, patch)
    assert [r["year"] for r in out["financials"]] == ["2025"]
    assert out["financials"][0]["revenue"] is None  # 2025 stayed null; 2026 dropped


def test_merge_trusted_source_extends_year_series():
    # add_years=True (yfinance): a 1-year LLM base is fleshed out to the full
    # series, existing values preserved, missing revenue filled. This is the
    # Hoa Phat case — research gave only 2025, yfinance supplies 2022-2025.
    base = _empty_report()
    base["financials"] = [{"year": "2025", "revenue": None, "net_income": 15515.0}]
    patch = {"financials": [
        {"year": "2022", "revenue": 141409.0, "net_income": 8483.0},
        {"year": "2023", "revenue": 118953.0, "net_income": 6835.0},
        {"year": "2024", "revenue": 138855.0, "net_income": 12021.0},
        {"year": "2025", "revenue": 156116.0, "net_income": 15453.0},
    ]}
    out = merge_extraction(base, patch, add_years=True)
    by_year = {r["year"]: r for r in out["financials"]}
    assert [r["year"] for r in out["financials"]] == ["2022", "2023", "2024", "2025"]
    assert by_year["2022"]["revenue"] == 141409.0     # new year added
    assert by_year["2025"]["revenue"] == 156116.0     # missing revenue filled
    assert by_year["2025"]["net_income"] == 15515.0   # research value preserved


def test_merge_seeds_financials_from_empty_base():
    # When the main pass found no years at all, the targeted pass may seed them.
    base = _empty_report()  # financials == []
    patch = {"financials": [
        {"year": "2024", "revenue": 58580.0},
        {"year": "2025", "revenue": 70000.0},
    ]}
    out = merge_extraction(base, patch)
    assert [(r["year"], r["revenue"]) for r in out["financials"]] == [
        ("2024", 58580.0), ("2025", 70000.0)]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}  {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
