"""Financial-report research orchestrator and CLI.

Research runs server-side as background interactions, so the CLI works
like a small job queue instead of blocking for minutes:

    python agent.py FPT              start a job, exit immediately
    python agent.py FPT, Apple       start several jobs at once
    python agent.py status           check jobs; finished ones get their
                                     data extracted and report written

Module layout:
    config.py       language + prompts
    model.py        Gemini client + model/agent names
    i18n.py         all user-facing text (report, charts, UI), per language
    schemas.py      the structured report data contracts (Pydantic)
    financials.py   pure report-dict logic (merge, gate, forecast filter)
    jobs.py         Job dataclass + JobStore (persistence)
    research.py     the Google / LLM API calls
    data_source.py  yfinance structured financials
    pipeline.py     build_report() — assembles a report from the sources
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
from research import check_research, start_research

store = JobStore()


def start_research_jobs(companies: list[str]) -> list[Job]:
    """Start one background research job per company; returns the new jobs."""
    jobs = store.load()
    new_jobs = []
    for company in companies:
        job = Job.new(company, start_research(company))
        jobs.append(job)
        new_jobs.append(job)
    store.save(jobs)
    return new_jobs


def clear_finished_jobs() -> list[Job]:
    """Drop done/failed jobs from history; keep running ones (whose research
    is still live on Google's side). Returns the remaining jobs."""
    remaining = [job for job in store.load() if job.state == "running"]
    store.save(remaining)
    return remaining


def refresh_jobs() -> tuple[list[Job], list[str]]:
    """Poll running jobs once; extract + write reports for finished ones.

    Each job is handled independently and its progress is saved as soon as it
    reaches a terminal state, so a failure on one job (e.g. a rate limit during
    extraction) neither aborts the batch nor rolls back another job that has
    already finished. A job that hits a transient error is left `running` so
    the next poll retries it.

    Returns (all jobs, human-readable event messages).
    """
    jobs = store.load()
    lab = get_labels()
    events = []

    for job in jobs:
        if job.state != "running":
            continue
        try:
            status, research_text = check_research(job.interaction_id)
        except Exception as e:
            events.append(f"[{job.company}] " + lab["ev_check_fail"].format(error=e))
            continue

        if status == "in_progress":
            continue
        if status != "completed":
            job.state = "failed"
            events.append(f"[{job.company}] " + lab["ev_failed"].format(status=status))
            store.save(jobs)
            continue

        try:
            data = build_report(job.company, research_text)
        except Exception as e:
            # A transient error (e.g. a rate limit) must not abort the batch or
            # discard the other jobs' progress: leave this job `running` so the
            # next poll retries it, and move on.
            events.append(
                f"[{job.company}] "
                + lab["ev_process_retry"].format(error=str(e)[:120]))
            continue

        # Only fail (so the user can re-run) if nothing usable came through.
        if not has_usable_financials(data):
            job.state = "failed"
            events.append(f"[{job.company}] " + lab["ev_no_data"])
            store.save(jobs)
            continue

        job.report_path = write_report(job.company, data, research_text)
        job.state = "done"
        events.append(f"[{job.company}] " + lab["ev_ready"])
        # Soft note: report written, but a critical figure (e.g. revenue) still
        # could not be found anywhere in the research.
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

    for job in start_research_jobs(companies):
        print(f"[{job.company}] research started (id: {job.interaction_id[:24]}...)")
    print("\nJobs are running server-side. Check them with: python agent.py status")
