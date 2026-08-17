"""Tests for the yfinance adapter. Run: python -m tests.test_market_data

The adapter (`_adapt`) is pure code, so these run with no network — they feed
it raw-currency rows (real Hoa Phat figures, ×1e9) and check the mapping,
billions normalisation, and derived computations.
"""

from finreport.tools.market_data import _adapt

B = 1e9


def _hpg_rows():
    return {
        "revenue": {2024: 138855.1 * B, 2025: 156116.1 * B},
        "gross_profit": {2025: 24497.8 * B},
        "operating_income": {2025: 20000.0 * B},
        "net_income": {2024: 12021.4 * B, 2025: 15453.2 * B},
        "cash": {2025: 8300.9 * B},
        "total_debt": {2025: 92174.2 * B},
        "equity": {2025: 100000.0 * B},
        "current_assets": {2025: 90000.0 * B},
        "current_liabilities": {2025: 60000.0 * B},
        "op_cashflow": {2025: 17365.9 * B},
        "capex": {2025: -25748.3 * B},
    }


def test_maps_and_normalises_to_billions():
    d = _adapt(_hpg_rows(), "VND")
    assert d["currency_unit"] == "tỷ VNĐ"
    by_year = {r["year"]: r for r in d["financials"]}
    assert by_year["2025"]["revenue"] == 156116.1
    assert by_year["2025"]["net_income"] == 15453.2
    assert by_year["2024"]["revenue"] == 138855.1  # earlier year kept, oldest first
    assert [r["year"] for r in d["financials"]] == ["2024", "2025"]


def test_computes_margins_from_latest_year():
    d = _adapt(_hpg_rows(), "VND")
    assert abs(d["margins"]["net"] - 9.9) < 0.2      # 15453.2 / 156116.1
    assert abs(d["margins"]["gross"] - 15.7) < 0.2   # 24497.8 / 156116.1


def test_computes_ratios_and_free_cash_flow():
    d = _adapt(_hpg_rows(), "VND")
    bs, cf = d["balance_sheet"], d["cash_flow"]
    assert bs["cash"] == 8300.9
    assert bs["debt"] == 92174.2
    assert abs(bs["debt_to_equity"] - 92.2) < 0.5    # 92174.2 / 100000
    assert abs(bs["current_ratio"] - 1.5) < 0.05     # 90000 / 60000
    assert cf["operating"] == 17365.9
    assert abs(cf["free"] - (-8382.4)) < 0.2         # 17365.9 + (-25748.3)


def test_usd_currency_unit():
    d = _adapt({"revenue": {2025: 416161e6 * 1e3}}, "USD")  # ~416B USD
    assert d["currency_unit"] == "USD billion"


def test_no_revenue_returns_empty():
    assert _adapt({"net_income": {2025: 100 * B}}, "VND") == {}


def test_row_values_prefers_broader_cash_then_falls_back():
    import datetime
    import pandas as pd
    from finreport.tools.market_data import _row_values

    broad = "Cash Cash Equivalents And Short Term Investments"
    strict = "Cash And Cash Equivalents"
    cols = [datetime.datetime(2025, 12, 31), datetime.datetime(2024, 12, 31)]
    df = pd.DataFrame({cols[0]: [23149.7, 1794.9], cols[1]: [20000.0, 1500.0]},
                      index=[broad, strict])
    # broad field present -> preferred
    assert _row_values(df, (broad, strict)) == {2025: 23149.7, 2024: 20000.0}
    # broad absent -> falls back to strict cash
    assert _row_values(df.drop(broad), (broad, strict)) == {2025: 1794.9, 2024: 1500.0}


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
