"""Tests for research.gather_context — search tool + plain synthesis.
Run: python test_research.py

Plain asserts, no framework. Tavily and Gemini are never called: we monkeypatch
research.search (the web-search tool) and research.client (the model).
"""

import config
import research


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text):
        self._text = text
        self.seen_contents = None

    def generate_content(self, model, contents, config=None):
        self.seen_contents = contents
        return _FakeResp(self._text)


class _FakeClient:
    def __init__(self, text):
        self.models = _FakeModels(text)


def _install(results_for_query, synth_text="SYNTHESIZED"):
    """Point research at fake search + client; return (calls, client)."""
    calls = []

    def fake_search(query, max_results=5, exclude_domains=None):
        calls.append({"query": query, "exclude_domains": exclude_domains})
        for needle, res in results_for_query.items():
            if needle in query:
                return res
        return []

    client = _FakeClient(synth_text)
    research.search = fake_search
    research.client = client
    return calls, client


def test_runs_one_search_per_template_with_exclude_domains():
    calls, _ = _install({"": []})  # "" matches every query -> []
    research.gather_context("FPT")
    assert len(calls) == len(config.SEARCH_QUERY_TEMPLATES)
    for c in calls:
        assert c["exclude_domains"] == config.EXCLUDE_DOMAINS
        assert "FPT" in c["query"]


def test_dedupes_results_by_uri_across_queries():
    dup = {"title": "Dup", "uri": "https://a.com", "content": "x"}
    only = {"title": "Only", "uri": "https://b.com", "content": "y"}
    # First template query returns dup; second returns dup again + only.
    q1 = config.SEARCH_QUERY_TEMPLATES[0].split()[1]  # a word from template 1
    q2 = config.SEARCH_QUERY_TEMPLATES[1].split()[1]  # a word from template 2
    calls, _ = _install({q1: [dup], q2: [dup, only]})
    text, sources = research.gather_context("FPT")
    assert [s["uri"] for s in sources] == ["https://a.com", "https://b.com"]


def test_synthesis_sees_result_content_and_returns_text_and_sources():
    res = [{"title": "CafeF", "uri": "https://cafef.vn/x", "content": "rev grew 20%"}]
    calls, client = _install({"": res}, synth_text="THE ANALYSIS")
    text, sources = research.gather_context("FPT")
    assert text == "THE ANALYSIS"
    assert sources == [{"title": "CafeF", "uri": "https://cafef.vn/x"}]
    assert "rev grew 20%" in client.models.seen_contents  # results fed to model


def test_no_results_returns_empty_and_skips_model():
    calls, client = _install({"": []})
    text, sources = research.gather_context("Nowhere Inc")
    assert text == ""
    assert sources == []
    assert client.models.seen_contents is None  # model never called


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
