"""Tests for pipeline.build_report — source routing. Run: python test_pipeline.py

Stubs the data-source and LLM calls so no network / API is used; verifies that
numbers come from the data source (authoritative) with narrative from the LLM,
and that a company with no ticker falls back to LLM number-extraction.
"""

import pipeline


def _run(stubs):
    saved = {k: getattr(pipeline, k) for k in stubs}
    for k, v in stubs.items():
        setattr(pipeline, k, v)
    try:
        return pipeline.build_report("Test Co", "research text")
    finally:
        for k, v in saved.items():
            setattr(pipeline, k, v)


def test_yfinance_primary_numbers_win_narrative_kept():
    data = _run({
        "resolve_ticker": lambda name: "TST",
        "fetch_financials": lambda tk: {
            "currency_unit": "USD billion",
            "financials": [{"year": "2025", "revenue": 500.0, "net_income": 50.0}],
            "margins": {"gross": 40.0, "operating": None, "net": 10.0},
            "balance_sheet": {"cash": 100.0},
            "cash_flow": {"operating": 60.0},
        },
        "extract_narrative": lambda text: {
            "summary": "S", "verdict": "V", "health": "good",
            "currency_unit": "", "segments": [{"name": "X", "revenue": 1}],
            "highlights": ["h"], "risks": ["r"],
        },
    })
    # numbers from the data source
    assert data["financials"][0]["revenue"] == 500.0
    assert data["currency_unit"] == "USD billion"   # data source overrides narrative
    # narrative from the LLM
    assert data["summary"] == "S"
    assert data["health"] == "good"
    assert data["segments"] == [{"name": "X", "revenue": 1}]


def test_fallback_to_llm_extraction_when_no_ticker():
    calls = {"extract": 0}

    def extract(text):
        calls["extract"] += 1
        return {"financials": [{"year": "2025", "revenue": 9.0, "net_income": 1.0}],
                "margins": {}, "balance_sheet": {}, "cash_flow": {},
                "summary": "F", "segments": []}

    data = _run({
        "resolve_ticker": lambda name: None,   # no ticker -> fallback path
        "extract_financials": extract,
    })
    assert calls["extract"] == 1                # LLM number-extraction used
    assert data["summary"] == "F"
    assert data["financials"][0]["revenue"] == 9.0


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
