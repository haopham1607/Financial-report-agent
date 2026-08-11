"""Tests for financials.py pure checks. Run: python test_financials.py

Plain asserts, no test framework — this project keeps its dependencies minimal.
"""

from financials import has_usable_financials, missing_critical_fields


def _report(financials=None, margins=None, balance_sheet=None, cash_flow=None):
    return {
        "financials": financials or [],
        "margins": margins or {"gross": None, "operating": None, "net": None},
        "balance_sheet": balance_sheet or {"cash": None, "debt": None,
                                           "debt_to_equity": None,
                                           "current_ratio": None},
        "cash_flow": cash_flow or {"operating": None, "free": None},
    }


# --- has_usable_financials ---

def test_empty_report_is_not_usable():
    assert has_usable_financials(_report()) is False


def test_revenue_makes_it_usable():
    assert has_usable_financials(_report(
        financials=[{"year": "2025", "revenue": 100.0, "net_income": None}])) is True


def test_net_income_alone_makes_it_usable():
    assert has_usable_financials(_report(
        financials=[{"year": "2025", "revenue": None, "net_income": 11232.0}])) is True


def test_margins_alone_make_it_usable():
    assert has_usable_financials(
        _report(margins={"gross": None, "operating": None, "net": 16.0})) is True


def test_balance_sheet_alone_makes_it_usable():
    assert has_usable_financials(_report(balance_sheet={
        "cash": 40153.0, "debt": None,
        "debt_to_equity": None, "current_ratio": None})) is True


def test_cash_flow_alone_makes_it_usable():
    assert has_usable_financials(
        _report(cash_flow={"operating": 10136.0, "free": None})) is True


def test_all_null_financials_is_not_usable():
    assert has_usable_financials(_report(financials=[
        {"year": "2023", "revenue": None, "net_income": None},
        {"year": "2024", "revenue": None, "net_income": None}])) is False


# --- missing_critical_fields ---

def test_missing_revenue_when_financials_empty():
    assert missing_critical_fields(_report()) == ["revenue"]


def test_missing_revenue_when_latest_year_has_no_revenue():
    assert missing_critical_fields(_report(financials=[
        {"year": "2024", "revenue": 100.0, "net_income": 10.0},
        {"year": "2025", "revenue": None, "net_income": 11.0}])) == ["revenue"]


def test_no_missing_when_latest_revenue_present():
    assert missing_critical_fields(_report(financials=[
        {"year": "2025", "revenue": 70000.0, "net_income": 11226.0}])) == []


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
