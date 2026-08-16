"""Tests for pipeline.build_report — now a thin wrapper over the agent loop.
Run: python -m tests.test_pipeline

Plain asserts, no framework. run_agent is stubbed, so no real API is used.
"""

import pipeline


def test_build_report_delegates_to_run_agent():
    seen = {}

    def fake_run_agent(company):
        seen["company"] = company
        return {"summary": "S", "health": "good",
                "financials": [{"year": "2025", "revenue": 100.0}]}

    saved = pipeline.run_agent
    pipeline.run_agent = fake_run_agent
    try:
        data = pipeline.build_report("FPT")
    finally:
        pipeline.run_agent = saved

    assert seen["company"] == "FPT"
    assert data["summary"] == "S"
    assert data["financials"][0]["revenue"] == 100.0


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
