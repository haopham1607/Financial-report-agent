"""Tests for web_search.py — the Tavily wrapper. Run: python test_web_search.py

Plain asserts, no test framework. Tavily is never called: tests monkeypatch
_client() with a fake, and the no-key path needs no client at all.
"""

from finreport.tools import web_search


class _FakeTavily:
    """Stand-in for TavilyClient; records the kwargs it was called with."""
    def __init__(self, payload):
        self.payload = payload
        self.seen = None

    def search(self, **kwargs):
        self.seen = kwargs
        return self.payload


def _use(fake):
    web_search._client = lambda: fake


# --- mapping Tavily results -> our shape ---

def test_maps_url_to_uri_and_keeps_title_content():
    _use(_FakeTavily({"results": [
        {"title": "FPT Q4", "url": "https://cafef.vn/fpt", "content": "revenue up"},
    ]}))
    out = web_search.search("FPT revenue")
    assert out == [{"title": "FPT Q4", "uri": "https://cafef.vn/fpt",
                    "content": "revenue up"}]


def test_drops_results_without_a_url():
    _use(_FakeTavily({"results": [
        {"title": "no link", "content": "x"},
        {"title": "ok", "url": "https://x.com", "content": "y"},
    ]}))
    out = web_search.search("q")
    assert [r["uri"] for r in out] == ["https://x.com"]


def test_passes_query_and_exclude_domains_to_tavily():
    fake = _FakeTavily({"results": []})
    _use(fake)
    web_search.search("hello", max_results=3, exclude_domains=["scribd.com"])
    assert fake.seen["query"] == "hello"
    assert fake.seen["max_results"] == 3
    assert fake.seen["exclude_domains"] == ["scribd.com"]


# --- graceful degradation ---

def test_no_key_returns_empty(monkeypatch=None):
    web_search._client = lambda: None
    assert web_search.search("anything") == []


def test_no_key_is_logged_not_silent():
    import logging

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    web_search._client = lambda: None
    logger = logging.getLogger(web_search.__name__)
    handler = _Capture()
    logger.addHandler(handler)
    try:
        assert web_search.search("anything") == []
    finally:
        logger.removeHandler(handler)

    assert len(records) == 1
    assert records[0].levelno == logging.WARNING


def test_tavily_error_returns_empty():
    class _Boom:
        def search(self, **kwargs):
            raise RuntimeError("network down")
    _use(_Boom())
    assert web_search.search("q") == []


def test_tavily_error_is_logged_as_warning():
    import logging

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    class _Boom:
        def search(self, **kwargs):
            raise RuntimeError("network down")

    _use(_Boom())
    logger = logging.getLogger(web_search.__name__)
    handler = _Capture()
    logger.addHandler(handler)
    try:
        assert web_search.search("acme financials") == []
    finally:
        logger.removeHandler(handler)

    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert "network down" in records[0].getMessage()


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
