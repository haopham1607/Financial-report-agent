"""Resilience tests for agent.refresh_jobs. Run: python test_agent.py

One job's failure (e.g. a rate limit while building its report) must not abort
the batch or roll back another job that already finished. `build_report` is
stubbed so no network / API quota is used — these test the orchestration and
resilience of the job loop, not the pipeline internals.
"""

import agent
from jobs import Job


class _FakeStore:
    """In-memory stand-in for JobStore that counts saves."""

    def __init__(self, jobs):
        self._jobs = jobs
        self.saves = 0

    def load(self):
        return self._jobs

    def save(self, jobs):
        self._jobs = jobs
        self.saves += 1


def _usable_data():
    # Passes has_usable_financials and leaves no missing_critical_fields, so
    # the job reaches "done".
    return {
        "financials": [{"year": "2025", "revenue": 100.0, "net_income": 10.0}],
        "margins": {"gross": None, "operating": None, "net": None},
        "segments": [],
        "balance_sheet": {"cash": None, "debt": None,
                          "debt_to_equity": None, "current_ratio": None},
        "cash_flow": {"operating": None, "free": None},
        "highlights": [], "risks": [],
        "summary": "", "verdict": "", "health": "good", "currency_unit": "x",
    }


def _run(jobs, build_impl):
    """Run refresh_jobs with stubbed I/O; restore originals afterwards."""
    saved = (agent.store, agent.build_report, agent.write_report)
    fake = _FakeStore(jobs)
    agent.store = fake
    agent.build_report = build_impl
    agent.write_report = lambda company, data: f"/reports/{company}.md"
    try:
        result_jobs, events = agent.refresh_jobs()
    finally:
        (agent.store, agent.build_report, agent.write_report) = saved
    return fake, result_jobs, events


def test_one_build_failure_does_not_abort_batch():
    jobs = [Job.new("A"), Job.new("B")]
    calls = {"n": 0}

    def build(company):
        calls["n"] += 1
        if company == "A":
            raise RuntimeError("429 rate limit")
        return _usable_data()

    _fake, result, _events = _run(jobs, build)
    by = {j.company: j.state for j in result}
    assert by["A"] == "running", by   # failed job left running to retry
    assert by["B"] == "done", by      # the other job still got processed
    assert calls["n"] == 2, calls     # B was attempted despite A failing


def test_finished_job_progress_is_persisted():
    jobs = [Job.new("A")]
    fake, result, _events = _run(jobs, lambda company: _usable_data())
    assert result[0].state == "done"
    assert result[0].report_path == "/reports/A.md"
    assert fake.saves >= 1            # state was written, not lost


def test_failure_does_not_roll_back_earlier_success():
    # A finishes, then B fails: A's "done" must survive B's error.
    jobs = [Job.new("A"), Job.new("B")]

    def build(company):
        if company == "B":
            raise RuntimeError("boom")
        return _usable_data()

    fake, result, _events = _run(jobs, build)
    by = {j.company: j.state for j in result}
    assert by["A"] == "done", by
    assert by["B"] == "running", by
    assert fake.saves >= 1           # A's completion was saved before B ran


def test_transient_errors_get_friendly_messages():
    # A 429/503 must be shown as an accurate, non-scary reason — not Google's raw
    # "you exceeded your quota, check your billing" text (which is misleading for
    # a transient per-minute rate limit or a busy service).
    from i18n import get_labels
    lab = get_labels()
    jobs = [Job.new("A"), Job.new("B")]

    def build(company):
        if company == "A":
            raise RuntimeError(
                "429 RESOURCE_EXHAUSTED. You exceeded your current quota, "
                "please check your plan and billing details.")
        raise RuntimeError("503 UNAVAILABLE. The model is experiencing high demand.")

    _fake, _result, events = _run(jobs, build)
    text = " ".join(events)
    assert lab["err_rate_limit"] in text   # 429 -> friendly rate-limit reason
    assert lab["err_busy"] in text          # 503 -> friendly busy reason
    assert "billing" not in text            # the raw misleading text is gone


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
