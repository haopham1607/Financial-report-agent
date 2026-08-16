"""Tests for report.py markdown — the segment section + its period label.
Run: python test_report.py

Plain asserts, no test framework — this project keeps its dependencies minimal.
write_report does file I/O, so each case writes into a throwaway temp dir and
cleans up. Assertions use get_labels() so they hold in either language.
"""

import os
import tempfile

from finreport.i18n import get_labels
from finreport.reporting import writer as report

lab = get_labels()


def _md(data: dict) -> str:
    """Write a report from `data` into a temp dir; return the markdown text."""
    tmp = tempfile.mkdtemp()
    report.REPORTS_DIR = tmp
    path = report.write_report("Test Co", data)
    text = open(path).read()
    os.remove(path)
    os.remove(path[:-3] + ".json")
    os.rmdir(tmp)
    return text


# --- the period label ---

def test_period_shown_in_segment_heading():
    md = _md({"segments": [{"name": "A", "revenue": 70},
                           {"name": "B", "revenue": 30}],
              "segment_period": "6 tháng đầu năm 2026"})
    assert f"## {lab['segments']} (6 tháng đầu năm 2026)" in md


def test_no_period_leaves_heading_without_parens():
    md = _md({"segments": [{"name": "A", "revenue": 10}],
              "segment_period": ""})
    assert f"## {lab['segments']}\n" in md
    assert f"## {lab['segments']} (" not in md


# --- shares mirror the donut (correct for absolute OR share-like inputs) ---

def test_shares_are_percent_of_total():
    md = _md({"segments": [{"name": "A", "revenue": 70},
                           {"name": "B", "revenue": 30}],
              "segment_period": "FY2025"})
    assert "- A: 70.0%" in md
    assert "- B: 30.0%" in md


def test_share_like_values_are_normalised():
    # The writer sometimes emits share-like numbers that don't sum to 100;
    # normalising by the total keeps the markdown consistent with the chart.
    md = _md({"segments": [{"name": "X", "revenue": 49.02},
                           {"name": "Y", "revenue": 51.0}],
              "segment_period": "FY2025"})
    assert "- X: 49.0%" in md  # 49.02 / 100.02
    assert "- Y: 51.0%" in md


# --- when there's nothing to show, the section is absent ---

def test_no_segments_skips_section():
    md = _md({"segments": [], "segment_period": ""})
    assert lab["segments"] not in md


def test_segments_with_only_none_revenue_skip_section():
    md = _md({"segments": [{"name": "A", "revenue": None}],
              "segment_period": "FY2025"})
    assert lab["segments"] not in md


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
