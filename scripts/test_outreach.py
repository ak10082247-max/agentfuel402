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
        self.assertFalse(eng.is_spam_repo("protoLabsAI", "protoLabsAI/protoAgent", "Production autonomous AI agent orchestration"))

    def test_commercial_builder_signal(self):
        self.assertFalse(eng.has_commercial_builder_signal({"company": "", "blog": "", "public_repos": 2, "followers": 1}, "anon@gmail.com"))
        self.assertTrue(eng.has_commercial_builder_signal({"company": "@AcmeAI", "blog": "", "public_repos": 2, "followers": 1}, "founder@gmail.com"))
        self.assertTrue(eng.has_commercial_builder_signal({"company": "", "blog": "", "public_repos": 2, "followers": 1}, "cto@acme.dev"))
        self.assertTrue(eng.has_commercial_builder_signal({"company": "", "blog": "", "public_repos": 12, "followers": 25}, "dev@gmail.com"))

    def test_concise_deliverable_pitches(self):
        for track in ("track_rugshield", "track_canaryguard", "track_agentfuel"):
            subj, body = eng.craft_pitch({
                "track": track,
                "name": "Alice Founder",
                "username": "alice",
                "repo": "acme/agent-router",
            })
            self.assertNotIn("`", body)
            self.assertNotIn("sniper", body.lower())
            self.assertLessEqual(body.count("https://"), 2)
            self.assertIn("Hey Alice,", body)
            self.assertIn("Arman", body)
            self.assertTrue(len(subj) < 70)


if __name__ == "__main__":
    unittest.main()
