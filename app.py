"""Streamlit frontend for the financial-report research agent.

Run with: streamlit run app.py
"""

import glob
import json
import os

import streamlit as st

import charts
from agent import clear_finished_jobs, refresh_jobs, queue_jobs, store
from i18n import get_labels
from report import REPORTS_DIR

L = get_labels()

st.set_page_config(page_title=L["app_title"], page_icon="📊", layout="wide")
st.title(L["app_title"])
st.caption(L["app_caption"])

STATE_ICONS = {"running": "🔄", "done": "✅", "failed": "❌"}
STATE_TEXT = {
    "running": L["state_running"],
    "done": L["state_done"],
    "failed": L["state_failed"],
}


def poll_jobs() -> None:
    """Build pending jobs (blocking) and remember the result for this session.
    Triggered ONLY by an explicit Refresh — never on page load or Start, so the
    slow build never blocks the initial render of the tabs and their buttons."""
    st.session_state.jobs, st.session_state.events = refresh_jobs()


def show_jobs() -> None:
    """Load the job list for display WITHOUT building — instant, non-blocking.
    Used on page load and right after Start so the UI (and its buttons) render
    immediately; the actual build runs later when the user clicks Refresh."""
    st.session_state.jobs = store.load()
    st.session_state.setdefault("events", [])


def render_report(data: dict) -> None:
    """Render one report as a visual dashboard from its JSON."""
    lab = L
    unit = data.get("currency_unit") or ""
    financials = data.get("financials") or []
    margins = data.get("margins") or {}
    segments = [s for s in (data.get("segments") or [])
                if s.get("revenue") is not None]

    st.header(f"{lab['title']}: {data.get('company', '')}")
    st.caption(data.get("date", "") + (f"  ·  {unit}" if unit else ""))

    # Verdict banner — status color + icon + plain-language label.
    health = data.get("health", "mixed")
    verdict = data.get("verdict", "")
    if health == "good":
        st.success(f"✅ **{lab['health_good']}** — {verdict}")
    elif health == "weak":
        st.error(f"🔴 **{lab['health_weak']}** — {verdict}")
    else:
        st.warning(f"⚠️ **{lab['health_mixed']}** — {verdict}")

    # KPI tiles with year-over-year growth arrows.
    latest = financials[-1] if financials else {}
    rev_g = charts.growth(financials, "revenue")
    ni_g = charts.growth(financials, "net_income")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        f"{lab['revenue']} ({latest.get('year', '—')})",
        charts.fmt_num(latest.get("revenue")),
        f"{rev_g:+.1f}% {lab['yoy']}" if rev_g is not None else None,
    )
    c2.metric(
        f"{lab['net_income']} ({latest.get('year', '—')})",
        charts.fmt_num(latest.get("net_income")),
        f"{ni_g:+.1f}% {lab['yoy']}" if ni_g is not None else None,
    )
    net_m = margins.get("net")
    c3.metric(lab["net"], f"{net_m}%" if net_m is not None else "—")

    # Charts — trend full width, then segment + profit side by side.
    if any(r.get("revenue") is not None for r in financials):
        charts.render_echart(charts.trend_chart(financials, lab, unit), height=360)

    ch1, ch2 = st.columns(2)
    with ch1:
        if segments:
            charts.render_echart(
                charts.segment_chart(segments, lab, data.get("segment_period", "")),
                height=340)
    with ch2:
        if net_m is not None:
            charts.render_echart(charts.profit_donut(net_m, lab), height=340)

    # Financial safety — balance sheet + cash flow.
    bs = data.get("balance_sheet") or {}
    cf = data.get("cash_flow") or {}
    de, cr = bs.get("debt_to_equity"), bs.get("current_ratio")
    has_bs = bs.get("cash") is not None or bs.get("debt") is not None
    has_cf = cf.get("operating") is not None or cf.get("free") is not None
    if has_bs or has_cf or de is not None or cr is not None:
        st.subheader(f"🛡️ {lab['safety']}")
        if de is not None or cr is not None:
            t1, t2 = st.columns(2)
            t1.metric(lab["debt_to_equity"], f"{de}%" if de is not None else "—")
            t2.metric(lab["current_ratio"], f"{cr}x" if cr is not None else "—")
        s1, s2 = st.columns(2)
        with s1:
            if has_bs:
                charts.render_echart(
                    charts.two_bar_chart(
                        lab["cash_vs_debt"], [lab["cash"], lab["debt"]],
                        [bs.get("cash"), bs.get("debt")],
                        [charts.CATEGORICAL[2], charts.CATEGORICAL[1]], unit),
                    height=320)
        with s2:
            if has_cf:
                charts.render_echart(
                    charts.two_bar_chart(
                        lab["cash_flow"], [lab["operating_cf"], lab["free_cf"]],
                        [cf.get("operating"), cf.get("free")],
                        [charts.S_BLUE, charts.S_BLUE], unit),
                    height=320)

    # Concise summary.
    st.subheader(lab["summary"])
    st.write(data.get("summary", ""))

    # Highlights and risks, side by side.
    col_h, col_r = st.columns(2)
    with col_h:
        st.subheader(f"✅ {lab['highlights']}")
        for item in data.get("highlights") or [lab["none"]]:
            st.markdown(f"- {item}")
    with col_r:
        st.subheader(f"⚠️ {lab['risks']}")
        for item in data.get("risks") or [lab["none"]]:
            st.markdown(f"- {item}")

    # Supporting figures table + full narrative, collapsed.
    if financials:
        with st.expander(lab["financials"]):
            rows = [
                {
                    lab["year"]: r.get("year", ""),
                    f"{lab['revenue']} ({unit})": charts.fmt_num(r.get("revenue")),
                    f"{lab['net_income']} ({unit})": charts.fmt_num(r.get("net_income")),
                }
                for r in financials
            ]
            st.table(rows)

    context = data.get("context")
    if context:
        with st.expander(lab["full_research"]):
            st.markdown(context)

    sources = data.get("sources") or []
    if sources:
        with st.expander(lab["sources"]):
            for s in sources:
                st.markdown(f"- [{s.get('title') or s.get('uri')}]({s.get('uri')})")


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
        # Queue only — do NOT build here. Building is slow and would block before
        # the tabs render, making their buttons vanish. Refresh runs the build.
        show_jobs()

# Load the job list once per browser session (page load). Building happens only
# on an explicit Refresh, so opening the app never blocks on pending work.
if "jobs" not in st.session_state:
    show_jobs()

for msg in st.session_state.events:
    st.info(msg)

jobs_tab, reports_tab = st.tabs([L["tab_jobs"], L["tab_reports"]])

# --- Jobs tab ---
with jobs_tab:
    col_refresh, col_clear = st.columns(2)
    with col_refresh:
        if st.button(L["refresh"], use_container_width=True):
            poll_jobs()
            st.rerun()
    with col_clear:
        # Clears done/failed jobs; running jobs stay so their research isn't
        # orphaned. Reports are untouched — this only clears history.
        if st.button(L["clear_finished"], use_container_width=True):
            clear_finished_jobs()
            poll_jobs()
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
