import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


class FakeLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class FakeActor:
    log = FakeLogger()

    def __init__(self, input_data):
        self.input_data = input_data
        self.charges = []
        self.pushed = []
        self.statuses = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get_input(self):
        return self.input_data

    async def charge(self, event_name, count=1):
        self.charges.append((event_name, count))

    async def push_data(self, data):
        self.pushed.append(data)

    async def set_status_message(self, msg):
        self.statuses.append(msg)


def _load_apify_main():
    if "apify" not in sys.modules:
        fake_apify = types.ModuleType("apify")
        fake_apify.Actor = FakeActor({})
        sys.modules["apify"] = fake_apify
    if "bs4" not in sys.modules:
        fake_bs4 = types.ModuleType("bs4")
        class _DummySoup:
            def __init__(self, *args, **kwargs):
                self.title = None
            def __call__(self, *args, **kwargs):
                return []
            def get_text(self, **kwargs):
                return ""
        fake_bs4.BeautifulSoup = _DummySoup
        sys.modules["bs4"] = fake_bs4
    if "httpx" not in sys.modules:
        fake_httpx = types.ModuleType("httpx")
        class _DummyURL:
            def __init__(self, u):
                self.host = ""
                self.scheme = "https"
                self.path = ""
        class _DummyClient:
            def __init__(self, *args, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
        fake_httpx.URL = _DummyURL
        fake_httpx.AsyncClient = _DummyClient
        sys.modules["httpx"] = fake_httpx
    import apify_main
    return apify_main


class ApifyBatchBillingTest(unittest.TestCase):
    def test_extract_max_leads_and_batch_urls(self):
        am = _load_apify_main()
        self.assertEqual(am._extract_max_leads({}), 50)
        self.assertEqual(am._extract_max_leads({"maxLeads": 250}), 250)
        self.assertEqual(am._extract_max_leads({"maxLeads": 999}), 500)
        self.assertEqual(am._extract_max_leads({"limit": 10}), 10)
        urls = am._parse_batch_urls({
            "urls": [
                "https://a.example",
                "https://a.example",
                "javascript:alert(1)",
                "http://b.example",
            ]
        })
        self.assertEqual(urls, ["https://a.example", "http://b.example"])

    def test_b2b_batch_charges_per_lead_delivered(self):
        am = _load_apify_main()
        fake_actor = FakeActor({"mode": "b2b-intent-leads", "maxLeads": 10})
        fake_leads = [{"company_name": f"Co{i}", "domain": f"co{i}.com"} for i in range(10)]
        async def fake_run(limit=50, category="all"):
            return {"status": "success", "timestamp_ms": 123456, "count": len(fake_leads), "leads": fake_leads}

        with patch.object(am, "Actor", fake_actor), patch.object(am, "run_b2b_leads", side_effect=fake_run):
            asyncio.run(am.main())

        self.assertEqual(fake_actor.charges, [("lead-signal-fetch", 10)])
        self.assertEqual(len(fake_actor.pushed), 1)
        self.assertEqual(len(fake_actor.pushed[0]), 10)
        self.assertEqual(fake_actor.pushed[0][0]["company_name"], "Co0")

    def test_markdown_urls_array_charges_only_succeeded(self):
        am = _load_apify_main()
        fake_actor = FakeActor({
            "mode": "llm-clean-markdown",
            "urls": ["https://ok1.test", "https://fail.test", "https://ok2.test"],
        })

        async def fake_md(u):
            if "fail" in u:
                return {"status": "error", "error": "upstream_target_unreachable", "target_url": u}
            return {"status": "success", "event_name": "clean-markdown-fetch", "feed": "/v1/fuel/llm-clean-markdown", "target_url": u, "markdown": "clean"}

        with patch.object(am, "Actor", fake_actor), patch.object(am, "run_clean_markdown", side_effect=fake_md):
            asyncio.run(am.main())

        self.assertEqual(fake_actor.charges, [("clean-markdown-fetch", 2)])
        self.assertEqual(len(fake_actor.pushed), 1)
        self.assertEqual(len(fake_actor.pushed[0]), 2)

    def test_all_failed_urls_never_charges(self):
        am = _load_apify_main()
        fake_actor = FakeActor({"mode": "ecom-price-stock", "urls": ["https://bad.test"]})

        async def fake_ecom(u):
            return {"status": "error", "error": "upstream_target_unreachable", "product_url": u}

        with patch.object(am, "Actor", fake_actor), patch.object(am, "run_ecom_price", side_effect=fake_ecom):
            asyncio.run(am.main())

        self.assertEqual(fake_actor.charges, [])
        self.assertEqual(fake_actor.pushed[0]["charged"], False)


if __name__ == "__main__":
    unittest.main()
