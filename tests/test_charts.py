"""Tests for charts.segment_chart label thresholding.
Run: python -m tests.test_charts

Plain asserts, no framework. Pure option-dict construction — no rendering.
"""

import charts
from i18n import get_labels

lab = get_labels()


def _labels_shown(segments):
    """[(name, is_label_shown)] for the built donut option."""
    opt = charts.segment_chart(segments, lab, "FY2025")
    return [(p["name"], "label" not in p) for p in opt["series"][0]["data"]]


def test_tiny_slices_are_unlabelled():
    # Nvidia's real shape: one dominant slice + three ~1% slivers whose labels
    # otherwise stack into a ladder of leader lines in one corner.
    shown = dict(_labels_shown([
        {"name": "Data Center", "revenue": 115.19},
        {"name": "Gaming", "revenue": 11.35},
        {"name": "ProViz", "revenue": 1.88},
        {"name": "Automotive", "revenue": 1.69},
        {"name": "Khác", "revenue": 0.39},
    ]))
    assert shown["Data Center"] is True    # 88% — labelled
    assert shown["Gaming"] is True         # 8.7% — labelled
    assert shown["ProViz"] is False        # 1.4% — hidden
    assert shown["Automotive"] is False    # 1.3% — hidden
    assert shown["Khác"] is False          # 0.3% — hidden


def test_evenly_split_segments_all_keep_labels():
    shown = dict(_labels_shown([
        {"name": "A", "revenue": 50.0},
        {"name": "B", "revenue": 30.0},
        {"name": "C", "revenue": 20.0},
    ]))
    assert all(shown.values())


def test_zero_total_does_not_crash():
    # All-zero revenues must not divide by zero.
    shown = dict(_labels_shown([{"name": "A", "revenue": 0},
                                {"name": "B", "revenue": 0}]))
    assert len(shown) == 2


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
