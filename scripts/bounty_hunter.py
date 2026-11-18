#!/usr/bin/env python3
"""
AgentFuel402 Automated GitHub Cash Bounty Scanner ($50-$500 Open PR Opportunities)
Finds legitimate, unclaimed TypeScript/Python/Node/FastAPI/MCP/Scraper bounties
from Algora, Polar, and repo bounty programs for autonomous PR submission.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import ssl
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    SSL_CTX = ssl._create_unverified_context()
except Exception:
    SSL_CTX = None

UA = "AgentFuel402-BountyHunter/1.0"
MIN_BOUNTY_USD = 50
MAX_BOUNTY_USD = 500
MIN_REPO_STARS = 5

TARGET_LANGUAGES = {"typescript", "javascript", "python"}
STACK_KEYWORDS = (
    "typescript", "javascript", "python", "node", "nodejs", "node.js",
    "fastapi", "express", "nextjs", "next.js", "cloudflare", "worker",
    "workers", "mcp", "scraper", "scrape", "crawl", "api", "sdk", "x402",
    "cli", "json", "webhook", "react", "vite",
)
SPAM_BOUNTY_REPOS = (
    "clankernation/",
    "ies-boilerroom/",
    "stegverse-labs/",
    "limitlessprojects/go-hybrid",
    "unsafelabs/bounty-hunters",
    "tine1117/oss-hunter-livefire",
    "apexopsstudio/ai-gitops-test-target",
    "zhangjiayang6835-cyber/bounty-plaza",
    "phankhoa95/oss-bot-trap-benchmark",
    "daisuke134/anicca",
    "ldavis2700/",
    "ikalus1988/",
    "relayhop/",
)
TRAP_REPO_TOKENS = ("bot-trap", "livefire", "test-target", "bounty-plaza", "oss-hunter")
AMOUNT_PATTERN = re.compile(
    r"(?:\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kK])?|"
    r"\b([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kK])?\s*(?:USDC|USD)\b)"
)


def _load_root_env():
    root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    if os.path.exists(root_env):
        try:
            with open(root_env, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass


def resolve_gh_token() -> str:
    _load_root_env()
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_PAT") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        try:
            out = subprocess.check_output(["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL).strip()
            if out.startswith(("gh", "github_pat_")):
                token = out
        except Exception:
            pass
    return token


def _gh_get(url: str, token: str = "", extra_accept: str = "", timeout: int = 8):
    headers = {
        "Accept": extra_accept or "application/vnd.github.v3+json",
        "User-Agent": UA,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_bounty_amount_usd(*texts: str) -> int | None:
    """Extract conservative cash bounty reward in USD ($50-$500 candidate band), respecting k suffix."""
    candidates = []
    for text in texts:
        if not text:
            continue
        for m in AMOUNT_PATTERN.finditer(text):
            raw_num = m.group(1) or m.group(3)
            k_flag = m.group(2) or m.group(4)
            if not raw_num:
                continue
            try:
                val = float(raw_num.replace(",", ""))
                if k_flag:
                    val *= 1000.0
                if 1 <= val <= 20000:
                    candidates.append(int(round(val)))
            except ValueError:
                continue
    in_band = [v for v in candidates if MIN_BOUNTY_USD <= v <= MAX_BOUNTY_USD]
    if in_band:
        return max(in_band)
    if candidates:
        return max(candidates)
    return None


def _matches_target_stack(repo_lang: str, text_blob: str) -> bool:
    lang_l = (repo_lang or "").lower().strip()
    if lang_l in TARGET_LANGUAGES:
        return True
    blob_l = (text_blob or "").lower()
    return any(re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", blob_l) for kw in STACK_KEYWORDS)


def _count_linked_prs_and_claims(repo_full: str, issue_num: int, token: str) -> tuple[int, int, str]:
    """Return (active_open_or_merged_prs, attempt_comments_count, comments_blob)."""
    open_prs = 0
    attempts = 0
    comments_blob = ""
    try:
        comments = _gh_get(
            f"https://api.github.com/repos/{repo_full}/issues/{issue_num}/comments?per_page=30",
            token=token,
            timeout=6,
        )
        if isinstance(comments, list):
            parts = []
            for c in comments:
                body = c.get("body") or ""
                author = (c.get("user") or {}).get("login") or ""
                if "/attempt" in body.lower() or "working on this" in body.lower():
                    attempts += 1
                if "algora" in author.lower() or "bounty" in body.lower() or "$" in body or "usdc" in body.lower():
                    parts.append(body[:800])
            comments_blob = "\n".join(parts)
    except Exception:
        pass

    try:
        timeline = _gh_get(
            f"https://api.github.com/repos/{repo_full}/issues/{issue_num}/timeline?per_page=30",
            token=token,
            extra_accept="application/vnd.github.mockingbird-preview+json",
            timeout=6,
        )
        if isinstance(timeline, list):
            for ev in timeline:
                if ev.get("event") == "cross-referenced":
                    src = (ev.get("source") or {}).get("issue") or {}
                    pr_meta = src.get("pull_request") or {}
                    if pr_meta and (src.get("state") == "open" or pr_meta.get("merged_at")):
                        open_prs += 1
    except Exception:
        pass

    return open_prs, attempts, comments_blob


def scan_open_cash_bounties(days: int = 14, top_n: int = 5, token: str = "") -> list[dict]:
    """Discover, filter, verify, and rank top unclaimed $50-$500 GitHub bounties."""
    gh_token = token or resolve_gh_token()
    since_recent = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    since_algora = (datetime.now(timezone.utc) - timedelta(days=max(days, 90))).strftime("%Y-%m-%d")

    queries = [
        f'is:issue is:open "algora-pbc" "$" updated:>={since_algora}',
        f'is:issue is:open "algora-pbc" language:TypeScript updated:>={since_algora}',
        f'is:issue is:open "algora-pbc" language:Python updated:>={since_algora}',
        f'is:issue is:open label:"💎 Bounty" language:TypeScript -repo:UnsafeLabs/Bounty-Hunters updated:>={since_algora}',
        f'is:issue is:open label:"💎 Bounty" language:Python updated:>={since_algora}',
        f'is:issue is:open label:"💎 Bounty" language:JavaScript updated:>={since_algora}',
        f'is:issue is:open label:bounty language:TypeScript updated:>={since_algora}',
        f'is:issue is:open "bounty" "USDC" language:TypeScript updated:>={since_recent}',
    ]

    raw_items = {}
    def _run_search(q: str):
        try:
            url = f"https://api.github.com/search/issues?q={urllib.parse.quote(q)}&sort=updated&order=desc&per_page=25"
            return _gh_get(url, token=gh_token, timeout=8).get("items") or []
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=6) as pool:
        for items in pool.map(_run_search, queries):
            for item in items:
                html_url = item.get("html_url") or ""
                if html_url and "/issues/" in html_url and html_url not in raw_items:
                    raw_items[html_url] = item

    repo_cache = {}
    repo_lock = threading.Lock()

    def _inspect_candidate(item: dict) -> dict | None:
        html_url = item.get("html_url") or ""
        repo_url = item.get("repository_url") or ""
        if "/repos/" not in repo_url:
            return None
        repo_full = repo_url.split("/repos/", 1)[1]
        rf_l = repo_full.lower()
        if any(rf_l.startswith(p) for p in SPAM_BOUNTY_REPOS) or any(tok in rf_l for tok in TRAP_REPO_TOKENS):
            return None

        with repo_lock:
            cached = repo_cache.get(repo_full)
        if cached is None:
            try:
                fetched = _gh_get(repo_url, token=gh_token, timeout=5)
            except Exception:
                fetched = {}
            with repo_lock:
                repo_cache[repo_full] = fetched
            repo_meta = fetched
        else:
            repo_meta = cached

        if not repo_meta or repo_meta.get("archived") or repo_meta.get("fork"):
            return None
        stars = int(repo_meta.get("stargazers_count") or 0)
        if stars < MIN_REPO_STARS:
            return None

        repo_lang = (repo_meta.get("language") or "").strip()
        labels = [lb.get("name", "") for lb in (item.get("labels") or []) if isinstance(lb, dict)]
        title = (item.get("title") or "").strip()
        body = (item.get("body") or "")[:3000]
        stack_blob = f"{repo_full} {repo_lang} {' '.join(labels)} {title} {body[:1200]}"
        if not _matches_target_stack(repo_lang, stack_blob):
            return None

        issue_num = int(item.get("number") or 0)
        open_prs, attempts, comments_blob = _count_linked_prs_and_claims(repo_full, issue_num, gh_token)
        if open_prs > 0:
            return None

        amount = parse_bounty_amount_usd(title, " ".join(labels), body, comments_blob)
        if amount is None or not (MIN_BOUNTY_USD <= amount <= MAX_BOUNTY_USD):
            return None

        score = 50.0
        has_algora = "algora" in (comments_blob + body).lower()
        if has_algora:
            score += 30
        if any("💎" in lb or "bounty" in lb.lower() for lb in labels):
            score += 20
        if repo_lang.lower() in TARGET_LANGUAGES:
            score += 15
        if any(tok in (" ".join(labels) + " " + title).lower() for tok in ("bug", "good first issue", "test", "vitest", "fix", "iso")):
            score += 15
        if len(body) >= 120:
            score += 10
        score += min(25.0, stars / 40.0)
        score += min(20.0, (amount - 50) / 20.0)
        score -= min(30.0, attempts * 8.0)

        return {
            "repo": repo_full,
            "number": issue_num,
            "title": title,
            "url": html_url,
            "amount_usd": amount,
            "language": repo_lang or "Multi",
            "stars": stars,
            "labels": labels,
            "open_prs": open_prs,
            "attempts": attempts,
            "algora": has_algora,
            "updated_at": item.get("updated_at") or "",
            "ease_score": round(score, 1),
            "solve_instruction": f"gh issue view {issue_num} --repo {repo_full} && clone, fix, test, and open PR referencing #{issue_num}",
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        scored = [r for r in pool.map(_inspect_candidate, list(raw_items.values())[:140]) if r]

    scored.sort(key=lambda r: (r["ease_score"], r["amount_usd"], r["stars"]), reverse=True)
    return scored[:top_n]


def format_bounty_scorecard_section(bounties: list[dict]) -> str:
    """Format top open cash bounties cleanly for the Daily Empire Scorecard digest."""
    if not bounties:
        return (
            "\n6. TOP OPEN GITHUB CASH BOUNTIES ($50-$500, UNCLAIMED):\n"
            "-----------------------------------------------------------------------------\n"
            "No verified unclaimed $50-$500 bounties matched right now.\n"
        )
    lines = [
        "\n6. TOP OPEN GITHUB CASH BOUNTIES ($50-$500, UNCLAIMED):",
        "-----------------------------------------------------------------------------",
    ]
    for idx, b in enumerate(bounties, 1):
        lines.append(
            f"{idx}. [${b['amount_usd']}] {b['repo']}#{b['number']} ({b['language']}, {b['stars']}*): {b['title'][:72]}"
        )
        lines.append(f"   URL:   {b['url']}")
        lines.append(f"   Solve: {b['solve_instruction']}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Scan top open GitHub cash bounties ($50-$500)")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days (default: 14)")
    parser.add_argument("--top", type=int, default=5, help="Number of top bounties to display (default: 5)")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    bounties = scan_open_cash_bounties(days=args.days, top_n=args.top)
    if args.json:
        print(json.dumps(bounties, indent=2))
    else:
        print(format_bounty_scorecard_section(bounties))


if __name__ == "__main__":
    main()
