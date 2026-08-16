"""Pure checks over a report dict — no network, no LLM, no I/O.

Used by the job loop to decide whether a built report is worth keeping and
whether to flag it incomplete. Kept dependency-free so it is trivially testable.
"""


def has_usable_financials(data: dict) -> bool:
    """True if the report has at least one real figure worth rendering.

    A report is worth keeping if any headline number came through, and is
    dropped only when it has essentially nothing (an all-null / empty result).
    """
    for row in data.get("financials") or []:
        if row.get("revenue") is not None or row.get("net_income") is not None:
            return True
    if any(v is not None for v in (data.get("margins") or {}).values()):
        return True
    bs = data.get("balance_sheet") or {}
    if bs.get("cash") is not None or bs.get("debt") is not None:
        return True
    cf = data.get("cash_flow") or {}
    if cf.get("operating") is not None or cf.get("free") is not None:
        return True
    return False


def missing_critical_fields(data: dict) -> list[str]:
    """Which must-have figures are absent.

    The dashboard's headline is revenue for the most recent fiscal year; when it
    is missing (e.g. the company isn't in the data source) the report is written
    but flagged incomplete.

    A blank summary means the agent finished without submitting a report (it hit
    its step limit), so the numbers are there but there is no assessment — that
    is flagged too, rather than passing as a finished report.
    """
    missing = []
    financials = data.get("financials") or []
    latest = financials[-1] if financials else {}
    if latest.get("revenue") is None:
        missing.append("revenue")
    if not (data.get("summary") or "").strip():
        missing.append("narrative")
    return missing
