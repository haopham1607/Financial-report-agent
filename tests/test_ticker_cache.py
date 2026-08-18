"""Tests for ticker_cache — the on-disk memory of resolved tickers.
Run: python -m tests.test_ticker_cache

Plain asserts, no framework. Every test repoints CACHE_FILE at a throwaway temp
file, so the real tickers.json is never touched.
"""

import json
import os
import tempfile

from finreport.tools import ticker_cache


def _use_temp_cache(contents=None):
    """Point the cache at a fresh temp file; optionally seed it."""
    path = os.path.join(tempfile.mkdtemp(), "tickers.json")
    if contents is not None:
        with open(path, "w") as fh:
            fh.write(contents if isinstance(contents, str) else json.dumps(contents))
    ticker_cache.CACHE_FILE = path
    return path


def test_put_then_get_round_trip():
    _use_temp_cache()
    ticker_cache.put("Vinamilk", "VNM.VN", "Vietnam Dairy Products JSC")
    assert ticker_cache.get("Vinamilk") == {
        "ticker": "VNM.VN", "name": "Vietnam Dairy Products JSC"}


def test_keys_ignore_case_and_whitespace():
    _use_temp_cache()
    ticker_cache.put("Vinamilk", "VNM.VN", "Vietnam Dairy")
    assert ticker_cache.get("  vinamilk  ")["ticker"] == "VNM.VN"
    assert ticker_cache.get("VINAMILK")["ticker"] == "VNM.VN"


def test_miss_returns_none():
    _use_temp_cache()
    assert ticker_cache.get("Nobody Inc") is None


def test_hand_written_bare_string_is_accepted():
    # The file is meant to be corrected by hand, where a plain string is natural.
    _use_temp_cache({"cmc": "CMG.VN"})
    assert ticker_cache.get("CMC") == {"ticker": "CMG.VN", "name": ""}


def test_existing_entry_is_not_overwritten():
    # A hand-correction must survive a later resolve of the same name.
    _use_temp_cache({"cmc": "CMG.VN"})
    ticker_cache.put("CMC", "CMC", "Commercial Metals Company")
    assert ticker_cache.get("CMC")["ticker"] == "CMG.VN"


def test_corrupt_file_reads_as_a_miss():
    _use_temp_cache("{not json at all")
    assert ticker_cache.get("Vinamilk") is None


def test_malformed_entry_is_replaced_by_a_good_one():
    _use_temp_cache({"vinamilk": {"ticker": None}})
    assert ticker_cache.get("Vinamilk") is None          # unusable -> a miss
    ticker_cache.put("Vinamilk", "VNM.VN", "Vietnam Dairy")
    assert ticker_cache.get("Vinamilk")["ticker"] == "VNM.VN"


def test_short_and_qualified_names_are_separate_entries():
    # A bad "cmc" entry must not poison "cmc vietnam".
    _use_temp_cache()
    ticker_cache.put("CMC", "CMC", "Commercial Metals Company")
    ticker_cache.put("CMC Vietnam", "CMG.VN", "CMC Corporation")
    assert ticker_cache.get("CMC")["ticker"] == "CMC"
    assert ticker_cache.get("CMC Vietnam")["ticker"] == "CMG.VN"


def test_empty_ticker_is_not_stored():
    _use_temp_cache()
    ticker_cache.put("Nowhere Inc", "", "")
    assert ticker_cache.get("Nowhere Inc") is None


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
