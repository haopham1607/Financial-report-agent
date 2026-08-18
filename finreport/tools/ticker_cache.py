"""Remember resolved tickers on disk, so a company is looked up only once.

resolve_ticker costs an LLM call, and requests — not tokens — are the binding
quota. The cache is a plain JSON file, meant to be readable and correctable by
hand:

    {"vinamilk": {"ticker": "VNM.VN", "name": "Vietnam Dairy Products JSC"}}

The company name is stored alongside the ticker so a wrong entry is obvious to a
human reading the file, and checkable by the agent at runtime.

Every failure degrades to a miss: a broken cache must never break a report.
"""

import json
import logging
import os

from finreport import ROOT

log = logging.getLogger(__name__)

CACHE_FILE = os.path.join(ROOT, "tickers.json")


def _key(company_name: str) -> str:
    """Cache key: case- and whitespace-insensitive. "cmc" and "cmc vietnam"
    stay distinct, so a bad short-name entry cannot poison a qualified one."""
    return (company_name or "").strip().lower()


def _load() -> dict:
    """The whole cache; {} when missing, empty, unreadable or not an object."""
    try:
        with open(CACHE_FILE) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get(company_name: str) -> dict | None:
    """{"ticker": ..., "name": ...} for a remembered company, else None.

    Tolerates a hand-written bare string ({"cmc": "CMG.VN"}), since that is what
    someone correcting the file by hand will naturally write.
    """
    entry = _load().get(_key(company_name))
    if isinstance(entry, str) and entry.strip():
        return {"ticker": entry.strip(), "name": ""}
    if isinstance(entry, dict):
        ticker = entry.get("ticker")
        if isinstance(ticker, str) and ticker.strip():
            return {"ticker": ticker.strip(), "name": str(entry.get("name") or "")}
    return None


def put(company_name: str, ticker: str, name: str = "") -> None:
    """Remember a resolve.

    A usable existing entry is never overwritten, so a hand-correction survives.
    An unusable one (malformed, empty ticker) is replaced. Write failures are
    swallowed — the cache may only ever save work, never block a report.
    """
    key = _key(company_name)
    if not key or not (ticker or "").strip():
        return
    if get(company_name):
        return
    cache = _load()
    cache[key] = {"ticker": ticker.strip(), "name": (name or "").strip()}
    try:
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(cache, fh, indent=2, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, CACHE_FILE)
    except OSError as e:
        log.warning("could not write the ticker cache: %s", e)
