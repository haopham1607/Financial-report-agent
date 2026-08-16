"""Financial-report orchestrator and CLI.

Work runs as a small local job queue: queue companies, then build them.

    python agent.py FPT              queue a job, exit immediately
    python agent.py FPT, Apple       queue several at once
    python agent.py status           build pending jobs; write their reports

Module layout:
    config.py       language + agent prompt + exclude list
    model.py        Gemini client + model name
    i18n.py         all user-facing text (report, charts, UI), per language
    schemas.py      the structured report data contracts (Pydantic)
    financials.py   pure report-dict logic (completeness gate, forecast filter)
    jobs.py         Job dataclass + JobStore (persistence)
    data_source.py  yfinance structured financials + name->ticker
    agent_loop.py   tool-calling loop (resolve_ticker, fetch_financials, web_search, submit_report)
    web_search.py   the web-search tool (Tavily)
    pipeline.py     build_report() — delegates to agent_loop.run_agent
    report.py       markdown + JSON report writer
    charts.py       ECharts builders + palette
    app.py          Streamlit frontend driving the same functions
"""

import os
import sys

from financials import has_usable_financials, missing_critical_fields
from i18n import get_labels
from jobs import Job, JobStore
from pipeline import build_report
from report import write_report

store = JobStore()


def queue_jobs(companies: list[str]) -> list[Job]:
    """Queue one job per company (state 'running'); returns the new jobs.

    The actual work (data fetch + grounded search + writer) runs on the next
    refresh_jobs() call.
    """
    jobs = store.load()
    new_jobs = []
    for company in companies:
        job = Job.new(company)
        jobs.append(job)
        new_jobs.append(job)
    store.save(jobs)
    return new_jobs


def clear_finished_jobs() -> list[Job]:
    """Drop done/failed jobs from history; keep pending (running) ones.
    Returns the remaining jobs."""
    remaining = [job for job in store.load() if job.state == "running"]
    store.save(remaining)
    return remaining


def _error_reason(error: Exception, lab: dict) -> str:
    """A short, accurate reason for a build failure.

    Transient API errors (429 per-minute rate limit, 503 high demand) get a plain
    explanation instead of Google's raw text — whose "you exceeded your quota,
    check your plan and billing" wording wrongly reads as a hard quota/key problem.
    """
    s = str(error)
    if "429" in s or "RESOURCE_EXHAUSTED" in s:
        return lab["err_rate_limit"]
    if "503" in s or "UNAVAILABLE" in s:
        return lab["err_busy"]
    return s[:120]


def refresh_jobs() -> tuple[list[Job], list[str]]:
    """Build every pending job and write its report.

    Each job is handled independently and saved as soon as it reaches a terminal
    state, so one job's failure (e.g. a rate limit) neither aborts the batch nor
    rolls back a job that already finished; a transient failure leaves the job
    `running` to retry on the next call.

    Returns (all jobs, human-readable event messages).
    """
    jobs = store.load()
    lab = get_labels()
    events = []

    for job in jobs:
        if job.state != "running":
            continue
        try:
            data = build_report(job.company)
        except Exception as e:
            # A transient error (e.g. a rate limit) must not abort the batch or
            # discard the other jobs' progress: leave this job `running` so the
            # next call retries it, and move on.
            events.append(
                f"[{job.company}] "
                + lab["ev_process_retry"].format(error=_error_reason(e, lab)))
            continue

        # Only fail (so the user can re-run) if nothing usable came through.
        if not has_usable_financials(data):
            job.state = "failed"
            events.append(f"[{job.company}] " + lab["ev_no_data"])
            store.save(jobs)
            continue

        job.report_path = write_report(job.company, data)
        job.state = "done"
        events.append(f"[{job.company}] " + lab["ev_ready"])
        # The agent decides its own path, so report what it actually did.
        trace = data.get("trace") or {}
        if trace:
            tools = ", ".join(f"{n}×{c}" for n, c in (trace.get("tools") or {}).items())
            events.append(f"[{job.company}] " + lab["ev_agent_trace"].format(
                steps=trace.get("steps", 0), tools=tools or "—"))
        # Soft note: report written, but a critical figure (e.g. revenue) could
        # not be found (e.g. the company isn't in the data source).
        if missing_critical_fields(data):
            events.append(f"[{job.company}] " + lab["ev_data_incomplete"])
        store.save(jobs)

    store.save(jobs)
    return jobs, events


if __name__ == "__main__":
    args = " ".join(sys.argv[1:]).strip()

    if args.lower() == "status":
        jobs, events = refresh_jobs()
        for msg in events:
            print(msg)
        if not jobs:
            print("No jobs yet. Start one with: python agent.py <company name>")
        else:
            print("\nAll jobs:")
            for job in jobs:
                line = f"  {job.company:<20} {job.state:<8} started {job.started_at}"
                if job.report_path:
                    line += f"  -> {os.path.basename(job.report_path)}"
                print(line)
        sys.exit(0)

    if not args:
        args = input("Company name(s), comma-separated: ").strip()
    companies = [c.strip() for c in args.split(",") if c.strip()]
    if not companies:
        print("No company name given.")
        sys.exit(1)

    for job in queue_jobs(companies):
        print(f"[{job.company}] queued")
    print("\nJobs queued. Build them with: python agent.py status")
