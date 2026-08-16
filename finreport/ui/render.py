"""The report dashboard: turns one report dict into the visual page.

Split from app.py (the page shell) so each file has one job.
"""

import streamlit as st

from finreport.i18n import get_labels
from finreport.reporting import charts

L = get_labels()


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
