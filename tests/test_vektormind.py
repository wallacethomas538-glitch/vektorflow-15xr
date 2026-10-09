"""Tests for vektormind.py — VektorMind dispatch parsing, provider-flexible
search honesty, and page browsing. No network: providers and HTTP faked."""
import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import external_tools
import vektormind as vm


class DispatchParseTests(unittest.TestCase):
    def test_at_mention(self):
        d = vm.parse_dispatch("@Rook check inventory levels")
        self.assertEqual(d["agent"], "Rook")
        self.assertEqual(d["task"], "check inventory levels")

    def test_dispatch_verb(self):
        d = vm.parse_dispatch("dispatch Scout to find trending dog toys")
        self.assertEqual(d["agent"], "Scout")
        self.assertIn("trending dog toys", d["task"])

    def test_ask_verb_case_insensitive(self):
        d = vm.parse_dispatch("ASK echo to draft a reply to the last customer email")
        self.assertEqual(d["agent"], "Echo")
        self.assertIn("draft a reply", d["task"])

    def test_have_verb_and_vektormind_prefix(self):
        d = vm.parse_dispatch("VektorMind, have Bundler to design a bundle for car care")
        self.assertEqual(d["agent"], "Bundler")

    def test_no_dispatch_plain_message(self):
        self.assertIsNone(vm.parse_dispatch("how many products do we have?"))

    def test_unknown_agent_no_dispatch(self):
        self.assertIsNone(vm.parse_dispatch("dispatch Bob to do things"))

    def test_resolve_name(self):
        self.assertEqual(vm.resolve_agent_name("viraldet"), "ViralDet")
        self.assertIsNone(vm.resolve_agent_name("nobody"))

    def test_roster_is_15(self):
        self.assertEqual(len(vm.roster()), 15)


class UrlAndTextTests(unittest.TestCase):
    def test_extract_urls(self):
        urls = vm.extract_urls("read https://example.com/a?x=1, and http://b.co/path.")
        self.assertEqual(urls, ["https://example.com/a?x=1", "http://b.co/path"])

    def test_html_to_text(self):
        raw = "<html><head><style>.x{}</style><script>bad()</script></head>" \
              "<body><h1>Hello</h1><p>World &amp; friends</p></body></html>"
        text = vm._html_to_text(raw)
        self.assertIn("Hello", text)
        self.assertIn("World & friends", text)
        self.assertNotIn("bad()", text)


class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_provider_configured_is_honest(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(vm.configured_search_providers(), [])
            with self.assertRaises(RuntimeError) as ctx:
                await vm.web_search("anything")
            self.assertIn("not configured", str(ctx.exception))

    async def test_tavily_used_when_only_tavily_configured(self):
        async def fake_tavily(query, max_results=10):
            return {"provider": "tavily", "query": query,
                    "results": [{"title": "T", "url": "https://x.co", "content": "C"}]}
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "k"}, clear=True), \
             mock.patch.object(external_tools, "tavily_search", fake_tavily):
            data = await vm.web_search("q")
        self.assertEqual(data["provider"], "tavily")
        self.assertEqual(data["results"][0]["description"], "C")

    async def test_brave_preferred_over_tavily(self):
        async def fake_brave(query, count=10):
            return {"provider": "brave", "query": query,
                    "results": [{"title": "B", "url": "https://b.co", "description": "D"}]}
        with mock.patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "k", "TAVILY_API_KEY": "k"}, clear=True), \
             mock.patch.object(external_tools, "brave_search", fake_brave):
            data = await vm.web_search("q")
        self.assertEqual(data["provider"], "brave")


class _FakeResponse:
    def __init__(self):
        self.headers = {"content-type": "text/html"}
        self.text = "<html><body><p>Real page content here.</p></body></html>"
        self.url = "https://example.com/"
    def raise_for_status(self):
        return None


class _FakeClient:
    def __init__(self, *a, **kw):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def get(self, url):
        return _FakeResponse()


class BrowseTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_non_http(self):
        with self.assertRaises(ValueError):
            await vm.browse_url("file:///etc/passwd")

    async def test_direct_fetch_extracts_text(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(vm.httpx, "AsyncClient", _FakeClient):
            page = await vm.browse_url("https://example.com/")
        self.assertEqual(page["provider"], "direct_fetch")
        self.assertIn("Real page content here.", page["content"])


if __name__ == "__main__":
    unittest.main()


class AdSpecialistKeyTests(unittest.TestCase):
    def test_accepts_pollinations_api_key_name(self):
        from vektorflow_agents import AdImageAgent
        with mock.patch.dict(os.environ, {"POLLINATIONS_API_KEY": "free-key"}, clear=True):
            agent = AdImageAgent()
        self.assertEqual(agent.api_key, "free-key")

    def test_ads_key_name_still_works(self):
        from vektorflow_agents import AdImageAgent
        with mock.patch.dict(os.environ, {"POLLINATIONS_ADS_KEY": "ads-key"}, clear=True):
            agent = AdImageAgent()
        self.assertEqual(agent.api_key, "ads-key")

    def test_missing_key_is_honest(self):
        import asyncio as _a
        from vektorflow_agents import AdImageAgent
        with mock.patch.dict(os.environ, {}, clear=True):
            agent = AdImageAgent()
        with self.assertRaises(RuntimeError) as ctx:
            _a.run(agent.generate_image("a dog toy"))
        self.assertIn("not configured", str(ctx.exception))
