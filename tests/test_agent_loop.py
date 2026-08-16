"""Tests for agent_loop.run_agent — the hand-built tool-calling loop.
Run: python -m tests.test_agent_loop

Plain asserts, no framework. The model turn (_model_turn) and the tool
implementations are monkeypatched, so no real API / network is used.
"""

import agent_loop

# Save the real _model_turn before any tests monkeypatch it
_real_model_turn = agent_loop._model_turn


def _script(turns):
    """Return a _model_turn stub yielding scripted turns.

    `turns` is a list of turns; each turn is a list of (tool_name, args) the
    'model' calls that step. The model content is a throwaway placeholder (the
    real loop appends it to `contents`, which the stub then ignores).
    """
    seq = iter(turns)

    def stub(contents):
        calls = next(seq)
        return object(), calls

    return stub


def test_happy_path_assembles_report():
    nums = {"currency_unit": "tỷ VNĐ",
            "financials": [{"year": "2025", "revenue": 100.0, "net_income": 10.0}],
            "margins": {"net": 10.0}}
    srch = [{"title": "CafeF", "uri": "http://cafef.vn/x", "content": "rev up"}]
    final = {"summary": "S", "verdict": "V", "health": "good",
             "segments": [{"name": "A", "revenue": 60}],
             "segment_period": "Cả năm 2025",
             "highlights": ["h"], "risks": ["r"], "analysis": "## Business\n..."}
    agent_loop._model_turn = _script([
        [("resolve_ticker", {"company_name": "X"})],
        [("fetch_financials", {"ticker": "TST"})],
        [("web_search", {"query": "X revenue"})],
        [("submit_report", final)],
    ])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: nums
    agent_loop.search = lambda query, exclude_domains=None: srch

    report = agent_loop.run_agent("X")
    assert report["summary"] == "S" and report["health"] == "good"
    assert report["context"] == "## Business\n..."            # analysis -> context
    assert report["segments"] == [{"name": "A", "revenue": 60}]
    assert report["segment_period"] == "Cả năm 2025"
    assert report["sources"] == [{"title": "CafeF", "uri": "http://cafef.vn/x"}]
    assert report["currency_unit"] == "tỷ VNĐ"               # numbers stamped
    assert report["financials"][0]["revenue"] == 100.0


def test_numbers_are_authoritative():
    # submit_report tries to sneak in numbers; the fetch_financials numbers win.
    nums = {"currency_unit": "USD billion",
            "financials": [{"year": "2025", "revenue": 500.0, "net_income": 50.0}]}
    final = {"summary": "S", "verdict": "V", "health": "good", "analysis": "a",
             "currency_unit": "FAKE", "financials": [{"year": "1999", "revenue": 1}]}
    agent_loop._model_turn = _script([
        [("fetch_financials", {"ticker": "TST"})],
        [("submit_report", final)],
    ])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: nums
    agent_loop.search = lambda query, exclude_domains=None: []

    report = agent_loop.run_agent("X")
    assert report["currency_unit"] == "USD billion"
    assert report["financials"][0]["revenue"] == 500.0


def test_dedupes_sources_across_searches():
    dup = {"title": "D", "uri": "http://a.com", "content": "x"}
    only = {"title": "O", "uri": "http://b.com", "content": "y"}
    agent_loop._model_turn = _script([
        [("web_search", {"query": "q1"})],
        [("web_search", {"query": "q2"})],
        [("submit_report",
          {"summary": "", "verdict": "", "health": "mixed", "analysis": "a"})],
    ])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: {}
    _results = iter([[dup], [dup, only]])
    agent_loop.search = lambda query, exclude_domains=None: next(_results)

    report = agent_loop.run_agent("X")
    assert [s["uri"] for s in report["sources"]] == ["http://a.com", "http://b.com"]


def test_max_steps_without_submit_returns_best_effort():
    # The model never submits (always searches). The loop must stop, not hang.
    agent_loop._model_turn = _script(
        [[("web_search", {"query": "q"})] for _ in range(agent_loop.MAX_STEPS + 2)])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: {}
    agent_loop.search = lambda query, exclude_domains=None: []

    report = agent_loop.run_agent("X")   # must return
    assert report["summary"] == ""       # best-effort empty narrative
    assert report["health"] == "mixed"


def test_model_turn_survives_empty_candidates():
    # A safety-filtered or degenerate Gemini response has no candidates.
    # The loop must not crash on indexing candidates[0].
    class FakeResponse:
        candidates = []

    class FakeClient:
        class Models:
            def generate_content(self, **kwargs):
                return FakeResponse()
        models = Models()

    original_client = agent_loop.client
    agent_loop.client = FakeClient()
    try:
        content, calls = _real_model_turn([])
        assert content is None
        assert calls == []
    finally:
        agent_loop.client = original_client


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
