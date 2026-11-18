import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bounty_hunter as bh
import unified_empire_engine as eng


class OutreachUpgradeTest(unittest.TestCase):
    def test_blocks_student_and_disposable_emails(self):
        self.assertFalse(eng.is_deliverable_personal_email("24bq1a05p6@vvit.net"))
        self.assertFalse(eng.is_deliverable_personal_email("b21cs042@gmail.com"))
        self.assertFalse(eng.is_deliverable_personal_email("alice@mit.edu"))
        self.assertFalse(eng.is_deliverable_personal_email("bob@cam.ac.uk"))
        self.assertFalse(eng.is_deliverable_personal_email("mar.kostrz@onet.pl"))
        self.assertFalse(eng.is_deliverable_personal_email("user@users.noreply.github.com"))
        self.assertFalse(eng.is_deliverable_personal_email("gitdigitalproducts232@manus.bot"))
        self.assertFalse(eng.is_deliverable_personal_email("info@hookdeck.com"))
        self.assertFalse(eng.is_deliverable_personal_email("ericy.song@mail.utoronto.ca"))

    def test_filters_low_intent_hobby_repos(self):
        self.assertTrue(eng.is_spam_repo("tjcrims0nx", "tjcrims0nx/OpenMind-Jailbreak-Lab", "jailbreak prompt testing"))
        self.assertTrue(eng.is_spam_repo("marekk13", "marekk13/PKP-Intercity-Train-Delay-Scraper", "train delay scraper"))
        self.assertTrue(eng.is_spam_repo("student1", "student1/capstone-llm-agent", "university project"))
        self.assertTrue(eng.is_spam_repo("aiqadam", "aiqadam/qadam-flow", "An open-source alternative to paid SaaS"))
        self.assertTrue(eng.is_spam_repo("selfhost", "selfhost/tool", "Free self-hosted alternative with no paid tiers"))
        self.assertTrue(eng.is_spam_repo("botdev", "botdev/polymarket-arbitrage-bot", "Polymarket prediction market bot"))
        self.assertTrue(eng.is_spam_repo("srivtx", "srivtx/sports-workbench", "Sports analytics and player pool database"))
        self.assertTrue(eng.is_spam_repo("sanjay-kv", "sanjay-kv/github-card-template", "Automated profile card"))
        self.assertTrue(eng.is_spam_repo("henryoman", "henryoman/pump-kit", "Pump.fun memecoin launcher kit"))
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
        self.assertIn("POACH_ISSUE_REPOS", src)
        self.assertIn("FORK_ECOSYSTEM_REPOS", src)

    def test_matches_track_keywords_strict_metadata(self):
        self.assertFalse(eng.matches_track_keywords("track_canaryguard", "dev/android-mail-client", "Fast email client for database notes", ["android", "kotlin"]))
        self.assertTrue(eng.matches_track_keywords("track_canaryguard", "dev/mcp-gateway", "LangChain MCP tool bridge", ["mcp", "agent"]))
        self.assertFalse(eng.matches_track_keywords("track_rugshield", "dev/firebase-notes", "Simple database UI without chains", ["react"]))
        self.assertTrue(eng.matches_track_keywords("track_rugshield", "dev/aerodrome-router", "Base swap router", ["defi", "base"]))
        self.assertFalse(eng.matches_track_keywords("track_agentfuel", "dev/rust-kernel", "toy OS kernel", ["rust"]))
        self.assertTrue(eng.matches_track_keywords("track_agentfuel", "dev/shopify-sync", "Automated Shopify webhook & lead enrichment", ["shopify"]))

    def test_extract_target_url_from_issue_skips_noise(self):
        txt = (
            "Screenshot: https://github.com/mendableai/firecrawl/assets/123/img.png "
            "and trying to scrape https://shop.example-merchant.com/products/widget failed with 403"
        )
        self.assertEqual(
            eng.extract_target_url_from_issue(txt),
            "https://shop.example-merchant.com/products/widget",
        )

    def test_concise_high_ticket_pitches_across_tracks(self):
        fake_b2b = [
            {"company": f"LaunchCo{i}", "domain": f"launch{i}.io", "headline": "AI workflow", "intent_score": 80}
            for i in range(1, 6)
        ]
        with patch.object(eng, "fetch_live_b2b_sample", return_value=fake_b2b):
            for track in ("track_rugshield", "track_canaryguard"):
                subj, body = eng.craft_pitch({
                    "track": track,
                    "lead_source": "recent_fork",
                    "ecosystem_repo": "coinbase/agentkit" if track == "track_rugshield" else "langgenius/dify",
                    "name": "Alice Founder",
                    "username": "alice",
                    "repo": "alice/agent-fork",
                    "diagnostic_summary": "Live check observed clean response in 7 ms.",
                })
                self.assertNotIn("`", body)
                self.assertNotIn("sniper", body.lower())
                self.assertIn("https://ak10082247-max.github.io/scanner.html", body)
                self.assertIn("https://agentfuel402.ak10082247.workers.dev/v1/checkout/api-key?plan=starter", body)
                self.assertLessEqual(body.count("https://"), 2)
                self.assertIn("Hey Alice,", body)
                self.assertIn("$29", body)
                self.assertIn("$5", body)
                self.assertTrue(len(subj) < 70)

            subj3, body3 = eng.craft_pitch({
                "track": "track_agentfuel",
                "lead_source": "issue_poach",
                "ecosystem_repo": "mendableai/firecrawl",
                "issue_number": 412,
                "name": "Bob Builder",
                "username": "bob",
                "repo": "mendableai/firecrawl",
                "rescue_result": {
                    "target_url": "https://acme-store.com/pricing",
                    "tokens": 310,
                    "engine": "edge-sanitizer",
                    "excerpt": "Enterprise pricing plans start at $49/mo",
                },
            })
            self.assertNotIn("`", body3)
            self.assertIn("#412", subj3)
            self.assertIn("LaunchCo5 (launch5.io)", body3)
            self.assertIn("https://apify.com/kuroxreal/llm-clean-markdown-ppe", body3)
            self.assertIn("https://agentfuel402.ak10082247.workers.dev/v1/checkout/api-key?plan=starter", body3)
            self.assertLessEqual(body3.count("https://"), 3)

    def test_bounty_amount_parser_respects_k_suffix(self):
        self.assertEqual(bh.parse_bounty_amount_usd("[ Bounty $8k ] Fix solidity", "💎 Bounty"), 8000)
        self.assertEqual(bh.parse_bounty_amount_usd("## 💎 $250 bounty • Outerbase"), 250)
        self.assertEqual(bh.parse_bounty_amount_usd("/bounty $5"), 5)
        self.assertEqual(bh.parse_bounty_amount_usd("Reward: 150 USDC"), 150)


if __name__ == "__main__":
    unittest.main()
