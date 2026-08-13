"""Tests for pipeline.build_report. Run: python test_pipeline.py

Stubs the data-source and model calls so no network / API is used; verifies
that numbers come from the data source (authoritative), the writer's structured
narrative is used, and the gathered context + sources are carried through.
"""

import pipeline


def _run(stubs):
    saved = {k: getattr(pipeline, k) for k in stubs}
    for k, v in stubs.items():
        setattr(pipeline, k, v)
    try:
        return pipeline.build_report("Test Co")
    finally:
        for k, v in saved.items():
            setattr(pipeline, k, v)


def test_numbers_from_data_source_narrative_from_writer():
    seen = {}

    def writer(company, numbers, context):
        seen["numbers"] = numbers
        seen["context"] = context
        return {"summary": "S", "verdict": "V", "health": "good",
                "currency_unit": "", "segments": [{"name": "X", "revenue": 1}],
                "highlights": ["h"], "risks": ["r"]}

    data = _run({
        "resolve_ticker": lambda name: "TST",
        "fetch_financials": lambda tk: {
            "currency_unit": "USD billion",
            "financials": [{"year": "2025", "revenue": 500.0, "net_income": 50.0}],
            "margins": {"gross": 40.0, "operating": None, "net": 10.0},
            "balance_sheet": {"cash": 100.0},
            "cash_flow": {"operating": 60.0},
        },
        "gather_context": lambda company, ticker="": (
            "## Business overview\n...", [{"title": "FPT", "uri": "http://fpt.com"}]),
        "write_narrative": writer,
    })
    # numbers from the data source
    assert data["financials"][0]["revenue"] == 500.0
    assert data["currency_unit"] == "USD billion"     # data source overrides writer
    # narrative from the writer
    assert data["summary"] == "S"
    assert data["health"] == "good"
    assert data["segments"] == [{"name": "X", "revenue": 1}]
    # writer received the yfinance numbers + the gathered context
    assert seen["numbers"]["financials"][0]["revenue"] == 500.0
    assert seen["context"].startswith("## Business overview")
    # context + sources carried through for display
    assert data["context"].startswith("## Business overview")
    assert data["sources"] == [{"title": "FPT", "uri": "http://fpt.com"}]


def test_no_ticker_yields_no_numbers_but_still_gathers_and_writes():
    calls = {"gather": 0, "write": 0}

    def writer(company, numbers, context):
        calls["write"] += 1
        assert numbers == {}          # no ticker -> no data-source numbers
        return {"summary": "F", "verdict": "", "health": "mixed",
                "currency_unit": "", "segments": [], "highlights": [], "risks": []}

    data = _run({
        "resolve_ticker": lambda name: None,
        "gather_context": lambda company, ticker="": (calls.__setitem__("gather", 1) or "ctx", []),
        "write_narrative": writer,
    })
    assert calls["gather"] == 1 and calls["write"] == 1
    assert data["summary"] == "F"
    assert not data.get("financials")  # no numbers without a ticker


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
