"""Streamlit page shell: the start form, the Jobs tab and the Reports tab.

The dashboard itself lives in finreport/ui/render.py. Run via the root app.py:
    streamlit run app.py
"""

import glob
import json
import os

import streamlit as st

from finreport.i18n import get_labels
from finreport.jobs.queue import (clear_finished_jobs, queue_jobs,
                                  refresh_jobs, store)
from finreport.reporting.writer import REPORTS_DIR
from finreport.ui.render import render_report

L = get_labels()

STATE_ICONS = {"running": "🔄", "done": "✅", "failed": "❌"}
STATE_TEXT = {
    "running": L["state_running"],
    "done": L["state_done"],
    "failed": L["state_failed"],
}


def poll_jobs() -> None:
    """Build pending jobs (blocking) and remember the result for this session.
    Runs only at the very END of the script (see the `build_now` block), after
    the tabs and their buttons have rendered, so the slow build never hides them."""
    st.session_state.jobs, st.session_state.events = refresh_jobs()


def show_jobs() -> None:
    """Load the job list for display WITHOUT building — instant, non-blocking.
    Renders the current queue (incl. freshly-queued running jobs) before the
    build runs, so the UI and its buttons appear immediately."""
    st.session_state.jobs = store.load()
    st.session_state.setdefault("events", [])


def main() -> None:
    """Draw the page. Streamlit re-runs this on every interaction."""
    st.set_page_config(page_title=L["app_title"], page_icon="📊", layout="wide")
    st.title(L["app_title"])
    st.caption(L["app_caption"])

    # --- Start form ---
    with st.form("start_form"):
        raw = st.text_input(L["company_input"], placeholder=L["company_placeholder"])
        submitted = st.form_submit_button(L["start_btn"])

    if submitted:
        companies = [c.strip() for c in raw.split(",") if c.strip()]
        if not companies:
            st.warning(L["enter_name"])
        else:
            for job in queue_jobs(companies):
                st.success(f"{L['started']} **{job.company}**")
            # Show the queued (running) jobs now, and flag the build to run at the END
            # of the script — after the tabs + buttons have rendered — so Start builds
            # immediately WITHOUT the slow work hiding the buttons mid-render.
            show_jobs()
            st.session_state.build_now = True

    # Load the job list once per browser session (page load). If anything is pending,
    # flag the build to run at the end (after the UI renders) — same as Start.
    if "jobs" not in st.session_state:
        show_jobs()
        if any(job.state == "running" for job in st.session_state.jobs):
            st.session_state.build_now = True

    for msg in st.session_state.events:
        st.info(msg)

    jobs_tab, reports_tab = st.tabs([L["tab_jobs"], L["tab_reports"]])

    # --- Jobs tab ---
    with jobs_tab:
        col_refresh, col_clear = st.columns(2)
        with col_refresh:
            if st.button(L["refresh"], use_container_width=True):
                # Defer the build to the end of the script (see build_now) so this
                # button's build never hides the widgets rendered after it.
                st.session_state.build_now = True
                st.rerun()
        with col_clear:
            # Clears done/failed jobs; running jobs stay so their research isn't
            # orphaned. Reports are untouched — this only clears history (no build).
            if st.button(L["clear_finished"], use_container_width=True):
                clear_finished_jobs()
                show_jobs()
                st.rerun()

        jobs = st.session_state.jobs
        if not jobs:
            st.caption(L["no_jobs"])
        else:
            for job in reversed(jobs):
                icon = STATE_ICONS.get(job.state, "❓")
                state = STATE_TEXT.get(job.state, job.state)
                label = f"{icon} {job.company} — {state} ({L['started_at']} {job.started_at})"
                with st.expander(label, expanded=(job.state == "running")):
                    if job.state == "done" and job.report_path:
                        st.write(L["job_done"].format(
                            name=os.path.basename(job.report_path)))
                    elif job.state == "running":
                        st.write(L["job_running"])
                    elif job.state == "failed":
                        st.error(L["job_failed"])

    # --- Reports tab ---
    with reports_tab:
        report_paths = sorted(
            glob.glob(os.path.join(REPORTS_DIR, "*.md")),
            key=os.path.getmtime,
            reverse=True,
        )
        if not report_paths:
            st.caption(L["no_reports"])
        else:
            names = [os.path.basename(p) for p in report_paths]
            chosen = st.selectbox(L["open_report"], names)
            path = report_paths[names.index(chosen)]
            with open(path) as fh:
                content = fh.read()

            json_path = path[:-3] + ".json"

            col_dl, col_del = st.columns(2)
            with col_dl:
                st.download_button(
                    L["download"], content, file_name=chosen,
                    mime="text/markdown", use_container_width=True,
                )
            with col_del:
                # Two-click delete: first click arms, second confirms.
                if st.session_state.get("delete_armed") == path:
                    if st.button(L["confirm_delete"], type="primary",
                                 use_container_width=True):
                        os.remove(path)
                        if os.path.exists(json_path):
                            os.remove(json_path)
                        st.session_state.pop("delete_armed", None)
                        st.rerun()
                else:
                    if st.button(L["delete"], use_container_width=True):
                        st.session_state.delete_armed = path
                        st.rerun()

            st.divider()

            # New financial reports have a companion JSON → rich dashboard.
            # Old reports (no JSON) fall back to their raw markdown.
            if os.path.exists(json_path):
                with open(json_path) as fh:
                    data = json.load(fh)
                render_report(data)
            else:
                st.markdown(content)


    # --- Deferred build (runs LAST) ---
    # Every widget above — the tabs, their buttons, the reports — has already
    # rendered by this point, so running the slow build here never blanks them out.
    # Set by Start, Refresh, or a first page load with pending jobs. A spinner shows
    # while it builds; then we rerun to display the finished reports.
    if st.session_state.pop("build_now", False):
        with st.spinner(L["building"]):
            poll_jobs()
        st.rerun()
