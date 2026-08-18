"""Tests for finreport/agent/loop.py's run_agent — the hand-built tool-calling loop.
Run: python -m tests.test_loop

Plain asserts, no framework. The model turn (_model_turn) and the tool
implementations are monkeypatched, so no real API / network is used.
"""

from finreport.agent import loop as agent_loop

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


def test_trace_records_tools_steps_and_submission():
    # The loop is nondeterministic, so it must report what it actually did.
    agent_loop._model_turn = _script([
        [("resolve_ticker", {"company_name": "X"})],
        [("web_search", {"query": "q1"})],
        [("web_search", {"query": "q2"})],
        [("submit_report", {"summary": "S", "verdict": "V", "health": "good",
                            "analysis": "A"})],
    ])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: {}
    agent_loop.search = lambda query, exclude_domains=None: []

    trace = agent_loop.run_agent("X")["trace"]
    assert trace["steps"] == 4
    assert trace["submitted"] is True
    assert trace["tools"] == {"resolve_ticker": 1, "web_search": 2,
                              "submit_report": 1}


def test_trace_marks_a_run_that_never_submitted():
    agent_loop._model_turn = _script(
        [[("web_search", {"query": "q"})] for _ in range(agent_loop.MAX_STEPS + 2)])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: {}
    agent_loop.search = lambda query, exclude_domains=None: []

    trace = agent_loop.run_agent("X")["trace"]
    assert trace["submitted"] is False
    assert trace["steps"] == agent_loop.MAX_STEPS


def test_model_turn_retries_on_rate_limit_then_succeeds():
    # One agent run makes several model calls back-to-back, which trips the
    # free tier's per-minute limit mid-loop. A transient 429/503 must pause and
    # retry the SAME turn, not throw away the steps already completed.
    calls = {"n": 0}
    slept = []

    class _Resp:
        candidates = []

    class _Models:
        def generate_content(self, model, contents, config=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
            return _Resp()

    class _Client:
        models = _Models()

    saved_client, saved_sleep = agent_loop.client, agent_loop.time.sleep
    agent_loop.client = _Client()
    agent_loop.time.sleep = lambda s: slept.append(s)
    try:
        content, out = _real_model_turn([])
    finally:
        agent_loop.client, agent_loop.time.sleep = saved_client, saved_sleep

    assert calls["n"] == 3          # failed twice, succeeded on the third
    assert len(slept) == 2          # backed off before each retry
    assert slept[0] < slept[1]      # increasing delay
    assert (content, out) == (None, [])


def test_model_turn_gives_up_after_max_retries():
    slept = []

    class _Models:
        def generate_content(self, model, contents, config=None):
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")

    class _Client:
        models = _Models()

    saved_client, saved_sleep = agent_loop.client, agent_loop.time.sleep
    agent_loop.client = _Client()
    agent_loop.time.sleep = lambda s: slept.append(s)
    try:
        raised = False
        try:
            _real_model_turn([])
        except RuntimeError:
            raised = True
    finally:
        agent_loop.client, agent_loop.time.sleep = saved_client, saved_sleep

    assert raised                   # still surfaces to the job loop for retry
    assert len(slept) == agent_loop.MAX_RETRIES


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


def test_model_turn_survives_missing_content():
    # A candidate can come back with content=None (e.g. MAX_TOKENS with no
    # parts produced). The loop must not crash indexing candidate.content.parts.
    class FakeCandidate:
        content = None

    class FakeResponse:
        candidates = [FakeCandidate()]

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


def test_failed_refetch_does_not_clobber_numbers():
    # The prompt invites the model to re-resolve/re-fetch; a second, failing
    # fetch_financials call must not wipe out numbers already captured.
    good_nums = {"currency_unit": "tỷ VNĐ",
                 "financials": [{"year": "2025", "revenue": 100.0,
                                "net_income": 10.0}]}
    agent_loop._model_turn = _script([
        [("fetch_financials", {"ticker": "TST"})],
        [("fetch_financials", {"ticker": "TST"})],
        [("submit_report",
          {"summary": "S", "verdict": "V", "health": "good", "analysis": "a"})],
    ])
    agent_loop.resolve_ticker = lambda name: "TST"
    _fetch_results = iter([good_nums, {}])
    agent_loop.fetch_financials = lambda tk: next(_fetch_results)
    agent_loop.search = lambda query, exclude_domains=None: []

    report = agent_loop.run_agent("X")
    assert report["currency_unit"] == "tỷ VNĐ"
    assert report["financials"][0]["revenue"] == 100.0


def test_submit_report_alongside_another_call_still_dispatches_it():
    # submit_report arriving first (or anywhere) in a multi-call turn must not
    # skip the turn's other calls.
    nums = {"currency_unit": "tỷ VNĐ",
            "financials": [{"year": "2025", "revenue": 100.0, "net_income": 10.0}]}
    final = {"summary": "S", "verdict": "V", "health": "good", "analysis": "a"}
    agent_loop._model_turn = _script([
        [("fetch_financials", {"ticker": "TST"}), ("submit_report", final)],
    ])
    agent_loop.resolve_ticker = lambda name: "TST"
    agent_loop.fetch_financials = lambda tk: nums
    agent_loop.search = lambda query, exclude_domains=None: []

    report = agent_loop.run_agent("X")
    assert report["financials"][0]["revenue"] == 100.0   # fetch was dispatched
    assert report["summary"] == "S"                       # narrative submitted


def test_assemble_coerces_missing_and_bad_fields():
    # submit_report args are untrusted model output: missing keys, an
    # out-of-enum health, and a non-numeric segment revenue must all coerce
    # to safe defaults instead of flowing None/garbage into report.write_report.
    final = {"segments": [{"name": "A", "revenue": "not a number"}],
             "health": "bogus", "analysis": None}
    report = agent_loop._assemble(final, {}, [])
    assert report["summary"] == ""
    assert report["highlights"] == []
    assert report["risks"] == []
    assert report["segments"] == []
    assert report["health"] == "mixed"
    assert report["context"] == ""


# --- the known-ticker note (cache hit lets the agent skip resolve_ticker) ---

def _capture_prompt(seen):
    """A _model_turn stub that records the opening prompt, then submits."""
    def stub(contents):
        seen["prompt"] = contents[0].parts[0].text
        return None, [("submit_report", {"summary": "S", "verdict": "V",
                                         "health": "good", "analysis": "A"})]
    return stub


def test_prompt_gains_the_known_ticker_on_a_cache_hit():
    seen = {}
    saved = agent_loop.ticker_cache.get
    agent_loop.ticker_cache.get = lambda c: {"ticker": "VNM.VN",
                                             "name": "Vietnam Dairy Products JSC"}
    agent_loop._model_turn = _capture_prompt(seen)
    try:
        agent_loop.run_agent("Vinamilk")
    finally:
        agent_loop.ticker_cache.get = saved
    assert "VNM.VN" in seen["prompt"]
    assert "Vietnam Dairy Products JSC" in seen["prompt"]


def test_prompt_is_unchanged_on_a_cache_miss():
    from finreport.agent.prompts import AGENT_PROMPT
    seen = {}
    saved = agent_loop.ticker_cache.get
    agent_loop.ticker_cache.get = lambda c: None
    agent_loop._model_turn = _capture_prompt(seen)
    try:
        agent_loop.run_agent("Vinamilk")
    finally:
        agent_loop.ticker_cache.get = saved
    assert seen["prompt"] == AGENT_PROMPT.format(company="Vinamilk")


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
