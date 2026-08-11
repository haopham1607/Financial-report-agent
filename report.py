"""Report writer: a markdown report plus a companion JSON of structured
data that the app uses to render charts."""

import datetime
import json
import os

from i18n import get_labels

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")


def _fmt(value, unknown: str) -> str:
    if value is None:
        return unknown
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def write_report(company: str, data: dict) -> str:
    """Write reports/{slug}_financial_{date}.md and a companion .json.

    `data` carries the analysis text and its sources (from the pipeline).
    Returns the markdown path.
    """
    lab = get_labels()
    context = data.get("context", "")
    sources = data.get("sources") or []
    os.makedirs(REPORTS_DIR, exist_ok=True)
    slug = "_".join(company.lower().split())
    now = datetime.datetime.now()
    date = now.date().isoformat()
    # Timestamp (date + time) in the filename so a re-run of the same company
    # on the same day never overwrites an earlier report.
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    base = os.path.join(REPORTS_DIR, f"{slug}_financial_{stamp}")
    md_path = base + ".md"

    # Companion JSON drives the charts and structured layout in the app.
    with open(base + ".json", "w") as fh:
        # context and sources already live in `data` (set by the pipeline).
        json.dump(
            {"company": company, "date": date, **data},
            fh,
            indent=2,
            ensure_ascii=False,
        )

    unit = data.get("currency_unit") or ""
    unit_suffix = f" ({unit})" if unit else ""

    lines = [
        f"# {lab['title']}: {company}",
        "",
        f"{lab['generated']}: {date}",
        "",
        f"## {lab['summary']}",
        "",
        data.get("summary", ""),
        "",
        f"## {lab['financials']}",
        "",
    ]

    financials = data.get("financials") or []
    if not financials:
        lines += [lab["none"], ""]
    else:
        lines.append(
            f"| {lab['year']} | {lab['revenue']}{unit_suffix} | "
            f"{lab['net_income']}{unit_suffix} |"
        )
        lines.append("| --- | --- | --- |")
        for row in financials:
            lines.append(
                f"| {row.get('year', '')} "
                f"| {_fmt(row.get('revenue'), lab['unknown'])} "
                f"| {_fmt(row.get('net_income'), lab['unknown'])} |"
            )
        lines.append("")

    margins = data.get("margins") or {}
    lines += [f"## {lab['margins']}", ""]
    lines.append(
        f"- {lab['gross']}: {_fmt(margins.get('gross'), lab['unknown'])}%  \n"
        f"- {lab['operating']}: {_fmt(margins.get('operating'), lab['unknown'])}%  \n"
        f"- {lab['net']}: {_fmt(margins.get('net'), lab['unknown'])}%"
    )
    lines.append("")

    # Revenue by segment, as % share (mirrors the donut, so it is correct whether
    # the writer gave absolute figures or shares). The period is stated in the
    # heading so an interim breakdown is never read as a full year.
    segments = [s for s in (data.get("segments") or [])
                if s.get("revenue") is not None]
    if segments:
        period = data.get("segment_period") or ""
        heading = lab["segments"] + (f" ({period})" if period else "")
        lines += [f"## {heading}", ""]
        total = sum(s["revenue"] for s in segments)
        for s in segments:
            share = f"{s['revenue'] / total * 100:.1f}%" if total else lab["unknown"]
            lines.append(f"- {s.get('name', '')}: {share}")
        lines.append("")

    for key in ("highlights", "risks"):
        lines += [f"## {lab[key]}", ""]
        items = data.get(key) or []
        if not items:
            lines += [lab["none"], ""]
        else:
            lines += [f"- {item}" for item in items] + [""]

    lines += [f"## {lab['full_research']}", "", context, ""]

    if sources:
        lines += [f"## {lab.get('sources', 'Sources')}", ""]
        lines += [f"{i}. [{s.get('title', s.get('uri', ''))}]({s.get('uri', '')})"
                  for i, s in enumerate(sources, 1)] + [""]

    with open(md_path, "w") as fh:
        fh.write("\n".join(lines))

    return md_path
