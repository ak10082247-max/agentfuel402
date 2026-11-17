import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unified_empire_engine as eng


class OutreachUpgradeTest(unittest.TestCase):
    def test_blocks_student_and_disposable_emails(self):
        self.assertFalse(eng.is_deliverable_personal_email("24bq1a05p6@vvit.net"))
        self.assertFalse(eng.is_deliverable_personal_email("b21cs042@gmail.com"))
        self.assertFalse(eng.is_deliverable_personal_email("alice@mit.edu"))
        self.assertFalse(eng.is_deliverable_personal_email("bob@cam.ac.uk"))
        self.assertFalse(eng.is_deliverable_personal_email("mar.kostrz@onet.pl"))
        self.assertFalse(eng.is_deliverable_personal_email("user@users.noreply.github.com"))

    def test_filters_low_intent_hobby_repos(self):
        self.assertTrue(eng.is_spam_repo("tjcrims0nx", "tjcrims0nx/OpenMind-Jailbreak-Lab", "jailbreak prompt testing"))
        self.assertTrue(eng.is_spam_repo("marekk13", "marekk13/PKP-Intercity-Train-Delay-Scraper", "train delay scraper"))
        self.assertTrue(eng.is_spam_repo("student1", "student1/capstone-llm-agent", "university project"))
        self.assertTrue(eng.is_spam_repo("aiqadam", "aiqadam/qadam-flow", "An open-source alternative to paid SaaS"))
        self.assertTrue(eng.is_spam_repo("selfhost", "selfhost/tool", "Free self-hosted alternative with no paid tiers"))
        self.assertTrue(eng.is_spam_repo("botdev", "botdev/polymarket-arbitrage-bot", "Polymarket prediction market bot"))
        self.assertFalse(eng.is_spam_repo("protoLabsAI", "protoLabsAI/protoAgent", "Production autonomous AI agent orchestration"))

    def test_commercial_builder_signal(self):
        self.assertFalse(eng.has_commercial_builder_signal({"company": "", "blog": "", "public_repos": 2, "followers": 1}, "anon@gmail.com"))
        self.assertTrue(eng.has_commercial_builder_signal({"company": "@AcmeAI", "blog": "", "public_repos": 2, "followers": 1}, "founder@gmail.com"))
        self.assertTrue(eng.has_commercial_builder_signal({"company": "", "blog": "", "public_repos": 2, "followers": 1}, "cto@acme.dev"))
        self.assertTrue(eng.has_commercial_builder_signal({"company": "", "blog": "", "public_repos": 12, "followers": 25}, "dev@gmail.com"))

    def test_blocks_official_vendor_orgs(self):
        for org in ("n8n-io", "langchain-ai", "coinbase", "anthropics", "openai", "apify", "modelcontextprotocol", "elizaOS", "activepieces"):
            self.assertTrue(eng.is_spam_repo(org, f"{org}/sdk", "Official SDK repository"))

    def test_star_band_limits(self):
        src = Path(__file__).resolve().with_name("unified_empire_engine.py").read_text(encoding="utf-8")
        self.assertIn("stars:1..300", src)
        self.assertNotIn("stars:>=", src)
        self.assertIn("if stars < 1 or stars > 300:", src)

    def test_matches_track_keywords_strict_metadata(self):
        self.assertFalse(eng.matches_track_keywords("track_canaryguard", "dev/android-mail-client", "Fast email client for database notes", ["android", "kotlin"]))
        self.assertTrue(eng.matches_track_keywords("track_canaryguard", "dev/mcp-gateway", "LangChain MCP tool bridge", ["mcp", "agent"]))
        self.assertFalse(eng.matches_track_keywords("track_rugshield", "dev/firebase-notes", "Simple database UI without chains", ["react"]))
        self.assertTrue(eng.matches_track_keywords("track_rugshield", "dev/aerodrome-router", "Base swap router", ["defi", "base"]))
        self.assertFalse(eng.matches_track_keywords("track_agentfuel", "dev/rust-kernel", "toy OS kernel", ["rust"]))
        self.assertTrue(eng.matches_track_keywords("track_agentfuel", "dev/shopify-sync", "Automated Shopify webhook & lead enrichment", ["shopify"]))

    def test_concise_deliverable_pitches(self):
        for track in ("track_rugshield", "track_canaryguard", "track_agentfuel"):
            subj, body = eng.craft_pitch({
                "track": track,
                "name": "Alice Founder",
                "username": "alice",
                "repo": "acme/agent-router",
                "diagnostic_summary": "Live check observed 412 clean tokens in 7 ms.",
            })
            self.assertNotIn("`", body)
            self.assertNotIn("sniper", body.lower())
            self.assertLessEqual(body.count("https://"), 2)
            self.assertIn("Hey Alice,", body)
            self.assertIn("Live check observed 412 clean tokens in 7 ms.", body)
            self.assertIn("$29", body)
            self.assertIn("$5", body)
            self.assertIn("Arman", body)
            self.assertTrue(len(subj) < 70)


if __name__ == "__main__":
    unittest.main()
