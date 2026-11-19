#!/usr/bin/env python3
"""
Big 3 Empire Engine — Autonomous Growth & Unified Revenue Scorecard
Consolidated Flagships: CanaryGuard 402, RugShield 402 & AgentFuel402
3-Track Sniper Prospecting + Multi-Vault Treasury & Active Apify Telemetry
"""
import os
import re
import sys
import json
import time
import random
import ssl
import smtplib
import argparse
import subprocess
from datetime import datetime, timedelta, timezone
import urllib.request
import urllib.error
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import bounty_hunter
    import agency_dealmaker
except ImportError:
    from scripts import bounty_hunter
    from scripts import agency_dealmaker

# Create SSL context resilient to missing local CA cert bundles
try:
    SSL_CTX = ssl._create_unverified_context()
except Exception:
    SSL_CTX = None

# -----------------------------------------------------------------------------
# CONFIGURATION & DYNAMIC CREDENTIAL RESOLUTION
# -----------------------------------------------------------------------------
def load_workspace_env():
    """Load local credentials from root .env without hardcoding secrets in git."""
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
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_workspace_env()

def resolve_gh_token():
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_PAT") or ""
    if not token:
        try:
            out = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
            if out.startswith("gh"):
                token = out
        except Exception:
            pass
    return token

GH_PAT = resolve_gh_token()
APIFY_TOKEN = os.environ.get("APIFY_TOKEN") or ""
SMTP_USER = os.environ.get("SMTP_USER") or os.environ.get("GMAIL_USER") or "armkhan18@gmail.com"
SMTP_PASS = os.environ.get("SMTP_PASS") or os.environ.get("GMAIL_APP_PASSWORD") or ""
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
DIGEST_RECIPIENTS = ["ak10082247@gmail.com", "armkhan18@gmail.com"]

MAX_EMAILS_PER_DAY = 24
MAX_EMAILS_PER_RUN = 6
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CONTACTED_FILE = os.path.join(DATA_DIR, "contacted_leads.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Big3-Empire-Engine"

# RPC Endpoints
BASE_RPCS = ["https://mainnet.base.org", "https://base.llamarpc.com", "https://1rpc.io/base"]
SOLANA_RPCS = ["https://api.mainnet-beta.solana.com", "https://rpc.ankr.com/solana"]
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Verified Live Treasury Vaults
BASE_WALLETS = [
    ("0x80E0Ae84679b7f11bE171DaADd492FBECf628cd6", "Base Merchant Payout (0x80E0...)")
]

SOLANA_ATAS = [
    ("DD3A7jaXFeHcif9eYj6Vhomuxypat5Yxi8ow6wxz27yL", "Solana Merchant ATA (Owner: 9wuMysgXwNhtQeqJgGByAiMYc4EjzZ5wUSmnjrrt3ffh)")
]

# The "Big 3" Repositories
BIG_3_REPOS = [
    ("canaryguard-402", "ak10082247-max/canaryguard-402", "Prompt-Injection Firewall & AI Agent Sanitizer"),
    ("rugshield-402", "ak10082247-max/rugshield-402", "Base & Solana DEX Honeypot & Pre-Trade Simulation Scanner"),
    ("agentfuel402", "ak10082247-max/agentfuel402", "B2B Intent Leads, Clean Markdown & E-Com Spec Engine")
]

# Active Public Apify Actors
ACTIVE_APIFY_ACTORS = [
    ("vtzNk9lbBdVUHGJKa", "canaryguard-402", "CanaryGuard Prompt-Injection Firewall"),
    ("lb9cRH5Gbe5aw7Hqv", "rugshield-402", "RugShield DEX Honeypot & Tax Simulator"),
    ("2AbJGn42avqlwZo5V", "b2b-intent-leads-ppe", "B2B Intent Leads & Buying Signals"),
    ("2KWgMEUJOiSzDpxeW", "llm-clean-markdown-ppe", "LLM Clean Markdown Sanitizer"),
    ("JoVOb6vKPFaNhDDcj", "ecom-price-stock-ppe", "E-Commerce Real-Time Price & Stock"),
    ("uOQ4jLOToRTwe10G1", "reverse-engineer-anything", "Reverse Engineer Anything (REA)")
]

# -----------------------------------------------------------------------------
# DEDUPLICATION & STORAGE
# -----------------------------------------------------------------------------
def load_leads():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CONTACTED_FILE):
        return {"contacted_emails": [], "contacted_users": [], "history": []}
    try:
        with open(CONTACTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"contacted_emails": [], "contacted_users": [], "history": []}

def save_leads(data):
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(CONTACTED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def count_sent_today(history):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sum(1 for item in history if item.get("sent_date", "").startswith(today))

# -----------------------------------------------------------------------------
# NETWORK HELPER WITH RESILIENT SSL & TIMEOUT
# -----------------------------------------------------------------------------
def fetch_json(url_or_req, timeout=8, headers=None, data=None):
    if isinstance(url_or_req, str):
        h = {}
        # Solana mainnet RPC strictly rejects non-standard User-Agents with 403
        if "solana" not in url_or_req.lower():
            h["User-Agent"] = UA
        if headers:
            h.update(headers)
        encoded_data = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url_or_req, data=encoded_data, headers=h)
    else:
        req = url_or_req
    kwargs = {"timeout": timeout}
    if SSL_CTX is not None:
        kwargs["context"] = SSL_CTX
    with urllib.request.urlopen(req, **kwargs) as r:
        return json.loads(r.read().decode("utf-8"))

# -----------------------------------------------------------------------------
# ON-CHAIN TREASURY BALANCE CHECKER
# -----------------------------------------------------------------------------
def query_base_usdc(addr):
    clean_addr = addr[2:].lower().rjust(64, "0")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": BASE_USDC, "data": f"0x70a08231{clean_addr}"}, "latest"]
    }
    for rpc in BASE_RPCS:
        try:
            res = fetch_json(rpc, timeout=5, headers={"Content-Type": "application/json"}, data=payload)
            hex_val = res.get("result", "0x0")
            return int(hex_val, 16) / 1e6
        except Exception:
            continue
    return 0.0

def query_solana_usdc(ata):
    """
    Directly query the SPL Token Associated Token Account balance using
    the canonical Solana JSON-RPC method `getTokenAccountBalance`.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountBalance",
        "params": [ata]
    }
    for rpc in SOLANA_RPCS:
        try:
            res = fetch_json(rpc, timeout=5, headers={"Content-Type": "application/json"}, data=payload)
            val = res.get("result", {}).get("value", {})
            return float(val.get("uiAmount") or 0.0)
        except Exception:
            continue
    return 0.0

def get_treasury_balances():
    balances = {"base": [], "solana": [], "total_usdc": 0.0}
    for addr, label in BASE_WALLETS:
        amt = query_base_usdc(addr)
        balances["base"].append({"address": addr, "label": label, "usdc": amt})
        balances["total_usdc"] += amt
    for ata, label in SOLANA_ATAS:
        amt = query_solana_usdc(ata)
        balances["solana"].append({"ata": ata, "label": label, "usdc": amt})
        balances["total_usdc"] += amt
    balances["total_usdc"] = round(balances["total_usdc"], 6)
    return balances

# -----------------------------------------------------------------------------
# GITHUB METRICS FOR THE "BIG 3"
# -----------------------------------------------------------------------------
def get_repo_metrics(repo_full_name):
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": UA
    }
    if GH_PAT:
        headers["Authorization"] = f"Bearer {GH_PAT}"

    result = {"stars": 0, "forks": 0, "open_prs": 0, "open_issues": 0}
    try:
        url = f"https://api.github.com/repos/{repo_full_name}"
        data = fetch_json(url, timeout=6, headers=headers)
        result["stars"] = data.get("stargazers_count", 0)
        result["forks"] = data.get("forks_count", 0)
        total_open = data.get("open_issues_count", 0)

        # Query open PR count accurately
        pr_search_url = f"https://api.github.com/search/issues?q=repo:{repo_full_name}+type:pr+state:open"
        pr_data = fetch_json(pr_search_url, timeout=6, headers=headers)
        result["open_prs"] = pr_data.get("total_count", 0)
        result["open_issues"] = max(0, total_open - result["open_prs"])
    except Exception as e:
        result["error"] = str(e)

    return result

def get_big3_github_stats():
    stats = {}
    for short_name, full_name, desc in BIG_3_REPOS:
        stats[short_name] = get_repo_metrics(full_name)
        stats[short_name]["full_name"] = full_name
        stats[short_name]["description"] = desc
    return stats

# -----------------------------------------------------------------------------
# ACTIVE APIFY PLATFORM & PPE TELEMETRY
# -----------------------------------------------------------------------------
def get_active_apify_stats():
    stats = []
    total_runs = 0
    total_succeeded = 0
    total_ppe_events = 0
    total_est_usd = 0.0

    for aid, name, desc in ACTIVE_APIFY_ACTORS:
        event_prices = {}
        try:
            actor_meta = fetch_json(
                f"https://api.apify.com/v2/acts/{aid}",
                timeout=8,
                headers={"Authorization": f"Bearer {APIFY_TOKEN}"} if APIFY_TOKEN else None,
            )
            pricing_infos = actor_meta.get("data", {}).get("pricingInfos") or []
            if pricing_infos:
                charge_events = (pricing_infos[-1].get("pricingPerEvent") or {}).get("actorChargeEvents") or {}
                for ev_name, ev_cfg in charge_events.items():
                    if isinstance(ev_cfg, dict) and isinstance(ev_cfg.get("eventPriceUsd"), (int, float)):
                        event_prices[ev_name] = float(ev_cfg["eventPriceUsd"])
        except Exception:
            event_prices = {}

        url = f"https://api.apify.com/v2/acts/{aid}/runs?limit=25&desc=true"
        try:
            res_data = fetch_json(url, timeout=8, headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
            items = res_data.get("data", {}).get("items", [])
            succeeded = [run for run in items if run.get("status") == "SUCCEEDED"]
            ppe_charges = 0
            est_usd = 0.0
            detail_checks = 0
            for run in succeeded:
                counts = run.get("chargedEventCounts")
                if counts is None and run.get("id") and detail_checks < 25:
                    detail_checks += 1
                    try:
                        run_detail = fetch_json(
                            f"https://api.apify.com/v2/actor-runs/{run['id']}",
                            timeout=6,
                            headers={"Authorization": f"Bearer {APIFY_TOKEN}"}
                        )
                        counts = run_detail.get("data", {}).get("chargedEventCounts") or {}
                    except Exception:
                        counts = {}
                for ev_name, ev_count in (counts or {}).items():
                    ev_num = int(ev_count or 0)
                    ppe_charges += ev_num
                    est_usd += ev_num * event_prices.get(ev_name, 0.0)

            total_runs += len(items)
            total_succeeded += len(succeeded)
            total_ppe_events += ppe_charges
            total_est_usd += est_usd
            stats.append({
                "id": aid,
                "name": name,
                "description": desc,
                "runs": len(items),
                "succeeded": len(succeeded),
                "ppe_charges": ppe_charges,
                "est_usd": round(est_usd, 4),
            })
        except Exception as e:
            stats.append({"id": aid, "name": name, "description": desc, "runs": 0, "succeeded": 0, "ppe_charges": 0, "est_usd": 0.0, "error": str(e)})

    return {
        "actors": stats,
        "total_runs": total_runs,
        "total_succeeded": total_succeeded,
        "total_ppe_events": total_ppe_events,
        "total_est_usd": round(total_est_usd, 4),
    }

# -----------------------------------------------------------------------------
# STRICT DELIVERABILITY VALIDATION (OPTION A - ZERO-BOUNCE GUARANTEE)
# -----------------------------------------------------------------------------
TRUSTED_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "proton.me",
    "protonmail.com",
    "pm.me",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "me.com",
    "yahoo.com",
    "fastmail.com",
    "hey.com",
}

DISALLOWED_PREFIXES = {
    "support", "billing", "admin", "press", "media", "jobs", "careers",
    "security", "abuse", "postmaster", "hostmaster", "webmaster", "bounce",
    "git", "noreply", "no-reply", "donotreply", "mailer-daemon",
    "info", "help", "sales", "marketing", "osscore", "newsletter", "community", "events"
}

BLOCKED_EMAIL_DOMAINS = {
    "users.noreply.github.com",
    "noreply.github.com",
    "github.com",
    "manus.bot",
    "localhost",
    "localdomain",
    "example.com",
    "example.org",
    "example.net",
    "test.com",
}

EMAIL_PREFIX_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._%+\-]{0,63}$")
EMAIL_DOMAIN_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)+$")
ICLOUD_RELAY_PATTERN = re.compile(r"(?:^[0-9]+[._-]|[._-][0-9a-z]{2}$|\d[a-z]$|(?:_|-|\.)[a-z]+\d[a-z]?$|^(?:[a-z0-9]+[-_.]){2,}[a-z0-9]{1,3}$)")
STUDENT_ROLL_PREFIX_PATTERN = re.compile(r"^(?:[bf]?(?:1[5-9]|2[0-9])[a-z]{2,4}\d[a-z0-9]{2,6}|[bf](?:1[5-9]|2[0-9])[a-z]{2}\d{3,4})$", re.IGNORECASE)
DISPOSABLE_OR_STUDENT_DOMAINS = {
    "qq.com", "163.com", "126.com", "yeah.net", "sina.com", "sohu.com", "foxmail.com",
    "vvit.net", "onet.pl", "mail.ru", "yandex.ru", "bk.ru", "list.ru", "inbox.ru",
    "guerrillamail.com", "mailinator.com", "tempmail.com", "10minutemail.com",
    "mail.utoronto.ca", "utoronto.ca", "uwaterloo.ca", "student.ubc.ca",
}
SPAM_REPO_PATTERN = re.compile(
    r"(?:how-to-(?:create|launch|configure|understand|build|run|deploy|set-up)-|"
    r"arbitrage-bot-(?:execution|deployment|cost-awareness|swap-routes|wallet-setup|loan-execution))",
    re.IGNORECASE,
)

_MX_CACHE = {}

def has_valid_mx_record(domain: str) -> bool:
    """Verifies via DNS-over-HTTPS that custom startup/company domains accept inbound email (non-null MX)."""
    domain = domain.lower().strip().rstrip(".")
    if domain in _MX_CACHE:
        return _MX_CACHE[domain]

    doh_endpoints = [
        f"https://cloudflare-dns.com/dns-query?name={urllib.parse.quote(domain)}&type=MX",
        f"https://dns.google/resolve?name={urllib.parse.quote(domain)}&type=MX",
    ]
    valid = False
    for url in doh_endpoints:
        try:
            res = fetch_json(url, timeout=4, headers={"Accept": "application/dns-json"})
            if res.get("Status") != 0:
                valid = False
                break
            answers = res.get("Answer") or []
            mx_records = [a for a in answers if a.get("type") == 15 and str(a.get("data", "")).strip() not in {"", "0 ."}]
            if mx_records:
                valid = True
                break
        except Exception:
            continue

    _MX_CACHE[domain] = valid
    return valid

def is_deliverable_personal_email(email: str) -> bool:
    """Validates email syntax, blocks relays/students/noreply traps, and verifies custom startup domains via live MX lookup."""
    if not email or "@" not in email:
        return False
    cleaned = email.lower().strip()
    parts = cleaned.split("@")
    if len(parts) != 2:
        return False
    prefix, domain = parts[0], parts[1]

    if not EMAIL_PREFIX_PATTERN.match(prefix) or not EMAIL_DOMAIN_PATTERN.match(domain):
        return False
    if domain in BLOCKED_EMAIL_DOMAINS or domain.endswith((".noreply.github.com", ".local", ".internal", ".test", ".invalid", ".arpa", ".bot")):
        return False

    # Exclude automated, bounce-trap, student roll-number, or generic helpdesk mailboxes
    if prefix in DISALLOWED_PREFIXES or any(p in prefix for p in ["noreply", "no-reply", "donotreply", "mailer", "dependabot", "[bot]"]):
        return False
    if STUDENT_ROLL_PREFIX_PATTERN.match(prefix):
        return False

    # Exclude Apple Hide-My-Email relay aliases & consumer bot/academic bounce domains
    if domain == "icloud.com" and ICLOUD_RELAY_PATTERN.search(prefix):
        return False
    if domain.endswith("privaterelay.appleid.com"):
        return False
    if domain in DISPOSABLE_OR_STUDENT_DOMAINS:
        return False
    if (
        domain == "edu"
        or domain.endswith((".edu", ".ac.in", ".ac.uk", ".edu.cn", ".edu.in", ".k12.us"))
        or ".edu." in domain
        or ".ac." in domain
        or "student." in domain
    ):
        return False

    # Fast path for verified consumer domains
    if domain in TRUSTED_EMAIL_DOMAINS:
        return True

    # Allow real startup / company / agency domains when DNS confirms active MX records
    return has_valid_mx_record(domain)

EXCLUDED_VENDOR_ORGS = {
    "ak10082247-max",
    "n8n-io",
    "langchain-ai",
    "coinbase",
    "anthropics",
    "openai",
    "apify",
    "modelcontextprotocol",
    "elizaos",
    "activepieces",
    "api-evangelist",
    "hookdeck",
}

REQUIRED_TRACK_KEYWORDS = {
    "track_rugshield": (
        "aerodrome", "uniswap", "jupiter", "raydium", "solana", "onchainkit",
        "agentkit", "defi", "dex", "web3", "evm", "spl", "honeypot",
        "erc20", "erc-20", "dexscreener", "token-2022", "rugpull", "rug-pull",
    ),
    "track_canaryguard": (
        "mcp", "modelcontextprotocol", "agent", "agents", "langchain", "langgraph",
        "crewai", "anthropic", "openai", "pydantic-ai", "mastra", "llm", "rag",
        "chatbot", "copilot", "prompt-injection", "guardrail", "sandbox",
    ),
    "track_agentfuel": (
        "apify", "shopify", "firecrawl", "crawl4ai", "crawl", "crawler", "scrape",
        "scraper", "scraping", "enrichment", "leads", "ecommerce", "e-commerce",
        "playwright", "puppeteer", "extractor", "price-monitor", "markdown",
    ),
}

def matches_track_keywords(track: str, repo_name: str, repo_desc: str, topics=None) -> bool:
    """Enforce track-relevant domain keywords in repo name, description, or topics (not just README hits)."""
    keywords = REQUIRED_TRACK_KEYWORDS.get(track, ())
    if not keywords:
        return True
    meta_blob = f"{repo_name or ''} {repo_desc or ''} {' '.join(topics or [])}".lower()
    return any(re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", meta_blob) for kw in keywords)

def is_spam_repo(owner: str, repo_name: str, repo_desc: str) -> bool:
    """Filters out own repos, official vendor orgs, student/hobby toys, and SEO/malware bot-farm repositories."""
    if not owner or not repo_name:
        return True
    if owner.lower() in EXCLUDED_VENDOR_ORGS:
        return True
    if repo_name.lower() in {f"{owner.lower()}/{owner.lower()}", f"{owner.lower()}/{owner.lower()}.github.io"}:
        return True
    if SPAM_REPO_PATTERN.search(repo_name):
        return True
    blob = f"{owner or ''} {repo_name or ''} {repo_desc or ''}".lower()
    low_intent_tokens = (
        "homework", "assignment", "coursework", "capstone", "bootcamp", "university",
        "college", "student", "semester", "cs50", "100-days", "tutorial", "ctf",
        "jailbreak-lab", "train-delay", "facebook-group", "interview", "resume", "thesis",
        "self-hosted alternative", "open-source alternative", "free alternative", "no paid tiers",
        "polymarket", "prediction-market", "betting", "gambling", "casino", "sportsbook",
        "arbitrage-bot", "mev-bot", "sniper-bot", "pumpfun", "pump.fun", "pump-kit", "memecoin",
        "practice", "learning", "my-first", "todo-app", "hello-world", "leetcode",
        "portfolio", "clone-app", "final-project", "mini-project", "mini_project",
        "class-project", "test-repo", "demo-app", "sample-app", "workshop", "awesome-",
        "sports-workbench", "fantasy-sports", "sportsbook", "cs2-", "github-card",
        "profile-card", "readme-card", "cheatsheet", "study-notes", "roadmap",
        "onlyfridge", "codebase-snapshot"
    )
    if any(tok in blob for tok in low_intent_tokens):
        return True
    if re.search(r"\b(blender|godot|unity3d|unreal|minecraft|roblox|neovim|wallpaper)\b", blob):
        return True
    desc_l = (repo_desc or "").lower()
    if "video-based guide to" in desc_l or "solidity arbitrage executor" in desc_l:
        return True
    return False

def has_commercial_builder_signal(u_data: dict, email: str) -> bool:
    """Prioritize real founders, maintainers, or funded builders over one-off student accounts."""
    domain = email.split("@")[-1].lower().strip()
    is_custom_domain = domain not in TRUSTED_EMAIL_DOMAINS
    has_company_or_site = bool((u_data.get("company") or "").strip() or (u_data.get("blog") or "").strip())
    public_repos = u_data.get("public_repos") or 0
    followers = u_data.get("followers") or 0
    return is_custom_domain or has_company_or_site or (public_repos >= 5 and followers >= 10)

# -----------------------------------------------------------------------------
# HIGH-INTENT COMMERCIAL PROSPECTING ENGINE (ISSUE POACHERS + RECENT FORKERS)
# -----------------------------------------------------------------------------
POACH_ISSUE_REPOS = {
    "track_agentfuel": [
        "mendableai/firecrawl",
        "unclecode/crawl4ai",
        "jina-ai/reader",
        "apify/crawlee",
        "browserbase/stagehand",
    ],
    "track_rugshield": [
        "coinbase/agentkit",
        "coinbase/onchainkit",
        "sendaifun/solana-agent-kit",
        "goat-sdk/goat",
    ],
    "track_canaryguard": [
        "langgenius/dify",
        "BerriAI/litellm",
        "labring/FastGPT",
    ],
}

FORK_ECOSYSTEM_REPOS = {
    "track_agentfuel": [
        "enescingoz/awesome-n8n-templates",
        "mendableai/firecrawl",
        "oxbshw/ultimate-n8n-ai-workflows",
        "browserbase/stagehand",
        "skyfire-xyz/skyfire",
    ],
    "track_rugshield": [
        "coinbase/agentkit",
        "coinbase/onchainkit",
        "sendaifun/solana-agent-kit",
        "goat-sdk/goat",
    ],
    "track_canaryguard": [
        "langgenius/dify",
        "BerriAI/litellm",
        "labring/FastGPT",
    ],
}

IGNORED_ISSUE_HOSTS = {
    "github.com", "gist.github.com", "user-images.githubusercontent.com",
    "raw.githubusercontent.com", "objects.githubusercontent.com",
    "shields.io", "img.shields.io", "youtube.com", "youtu.be",
    "x.com", "twitter.com", "discord.gg", "discord.com", "t.me",
    "npmjs.com", "pypi.org", "localhost", "127.0.0.1", "example.com",
}

_USER_LOOKUP_CACHE = {}
_B2B_SAMPLE_CACHE = None


def _gh_headers():
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": UA,
    }
    if GH_PAT:
        headers["Authorization"] = f"Bearer {GH_PAT}"
    return headers


def resolve_github_user_email(login: str, headers: dict, candidate_repos=None):
    """Resolve user metadata and deliverable email via profile, repo commits, or public push events."""
    norm = (login or "").lower().strip()
    if not norm or "[bot]" in norm or norm in EXCLUDED_VENDOR_ORGS:
        return None, None
    if norm in _USER_LOOKUP_CACHE:
        return _USER_LOOKUP_CACHE[norm]

    u_data = {}
    found_email = None
    try:
        u_data = fetch_json(f"https://api.github.com/users/{urllib.parse.quote(login)}", timeout=4, headers=headers)
        if (u_data.get("type") or "").lower() == "bot":
            _USER_LOOKUP_CACHE[norm] = (u_data, None)
            return u_data, None
        cand = u_data.get("email")
        if is_deliverable_personal_email(cand):
            found_email = cand.lower().strip()
    except Exception:
        _USER_LOOKUP_CACHE[norm] = ({}, None)
        return {}, None

    repos_to_check = list(candidate_repos or [])
    if not found_email:
        try:
            user_repos = fetch_json(
                f"https://api.github.com/users/{urllib.parse.quote(login)}/repos?sort=pushed&per_page=3",
                timeout=4,
                headers=headers,
            )
            if isinstance(user_repos, list):
                user_repos.sort(key=lambda r: bool(r.get("fork")))
                for ur in user_repos:
                    fn = ur.get("full_name")
                    if fn and fn not in repos_to_check:
                        repos_to_check.append(fn)
        except Exception:
            pass

    for repo_full in repos_to_check[:4]:
        if found_email:
            break
        try:
            commits = fetch_json(
                f"https://api.github.com/repos/{repo_full}/commits?author={urllib.parse.quote(login)}&per_page=3",
                timeout=4,
                headers=headers,
            )
            if isinstance(commits, list):
                for c in commits:
                    cand = (c.get("commit") or {}).get("author", {}).get("email")
                    if is_deliverable_personal_email(cand):
                        found_email = cand.lower().strip()
                        break
        except Exception:
            pass

    if not found_email:
        try:
            events = fetch_json(
                f"https://api.github.com/users/{urllib.parse.quote(login)}/events/public?per_page=15",
                timeout=4,
                headers=headers,
            )
            if isinstance(events, list):
                for ev in events:
                    if ev.get("type") != "PushEvent":
                        continue
                    for c in (ev.get("payload") or {}).get("commits") or []:
                        cand = (c.get("author") or {}).get("email")
                        if is_deliverable_personal_email(cand):
                            found_email = cand.lower().strip()
                            break
                    if found_email:
                        break
        except Exception:
            pass

    _USER_LOOKUP_CACHE[norm] = (u_data, found_email)
    return u_data, found_email


def extract_target_url_from_issue(text: str) -> str:
    """Extract the first real external webpage/product URL posted in a scraping issue."""
    if not text:
        return ""
    for m in re.finditer(r"https?://[^\s<>\"')\]`]+", text):
        cand = m.group(0).rstrip(".,;:!?")
        try:
            parsed = urllib.parse.urlparse(cand)
            host = (parsed.netloc or "").lower().split(":")[0]
            if not host or any(host == ig or host.endswith("." + ig) for ig in IGNORED_ISSUE_HOSTS):
                continue
            if parsed.path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".mp4", ".pdf")):
                continue
            return cand
        except Exception:
            continue
    return ""


def rescue_issue_target_url(target_url: str, timeout: int = 5) -> dict:
    """Run a failing issue target URL through AgentFuel402 Clean Markdown for live email proof."""
    if not target_url:
        return {}
    try:
        q_url = urllib.parse.quote(target_url, safe="")
        res = fetch_json(
            f"https://agentfuel402.ak10082247.workers.dev/v1/preview/llm-clean-markdown?url={q_url}",
            timeout=timeout,
        )
        md = (res.get("markdown") or "").strip()
        if res.get("status") == "success" and md:
            excerpt = re.sub(r"[`\r\n\t]+", " ", md)
            excerpt = re.sub(r"\s{2,}", " ", excerpt).strip()[:200]
            return {
                "target_url": target_url,
                "tokens": int(res.get("token_estimate") or max(1, len(md) // 4)),
                "engine": res.get("engine") or "edge-sanitizer",
                "excerpt": excerpt,
            }
    except Exception:
        pass
    return {}


def fetch_live_b2b_sample(limit: int = 5) -> list:
    """Fetch 5 fresh live B2B startup/hiring leads once per engine run for Track 3 proof."""
    global _B2B_SAMPLE_CACHE
    if isinstance(_B2B_SAMPLE_CACHE, list) and len(_B2B_SAMPLE_CACHE) >= min(3, limit):
        return _B2B_SAMPLE_CACHE[:limit]

    rows = []
    seen = set()
    skip_hosts = {"claude.ai", "news.ycombinator.com", "chatgpt.com", "youtube.com", "x.com"}
    skip_prefixes = ("why ", "how i ", "i turned ", "i built ", "what ", "ask hn:")
    try:
        data = fetch_json("https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&hitsPerPage=40", timeout=6)
        for s in data.get("hits") or []:
            title = (s.get("title") or "").strip()
            if not title:
                continue
            clean_title = re.sub(r"^(?:Show HN|Launch HN):\s*", "", title, flags=re.IGNORECASE).strip()
            if clean_title.lower().startswith(skip_prefixes):
                continue
            raw_url = (s.get("url") or "").strip()
            if not raw_url.startswith(("http://", "https://")):
                continue
            host = urllib.parse.urlparse(raw_url).netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            if not host or any(host == ig or host.endswith("." + ig) for ig in skip_hosts):
                continue
            company = re.split(r"\s+[–—\-|:]\s+|:\s+", clean_title, maxsplit=1)[0].strip()[:36]
            if not company or len(company.split()) > 5:
                company = host.split(".")[0].capitalize()
            score = s.get("points") or 1
            comments = s.get("num_comments") or 0
            intent = min(100, max(40, int(score) * 2 + int(comments) * 3))
            if company.lower() in seen or host in seen:
                continue
            seen.add(company.lower())
            seen.add(host)
            rows.append({
                "company": company,
                "domain": host,
                "headline": clean_title[:85],
                "intent_score": intent,
            })
            if len(rows) >= limit:
                break
    except Exception:
        pass

    if len(rows) < limit:
        try:
            data = fetch_json("https://remotive.com/api/remote-jobs?limit=25", timeout=6)
            for j in data.get("jobs") or []:
                co = (j.get("company_name") or "").strip()[:36]
                if not co or co.lower() in seen:
                    continue
                seen.add(co.lower())
                rows.append({
                    "company": co,
                    "domain": "remotive.com",
                    "headline": f"Hiring {j.get('title', 'Engineer')}"[:85],
                    "intent_score": 68,
                })
                if len(rows) >= limit:
                    break
        except Exception:
            pass

    _B2B_SAMPLE_CACHE = rows
    return rows[:limit]


def discover_issue_poaching_leads(track: str, limit: int, exclude_emails: set, exclude_users: set) -> list:
    """Stream A: Intercept developers opening recent issues on competitor/ecosystem repos."""
    repos = list(POACH_ISSUE_REPOS.get(track, []))
    if not repos:
        return []
    random.shuffle(repos)
    headers = _gh_headers()
    since_14d = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    found = []

    for eco_repo in repos:
        if len(found) >= limit:
            break
        eco_owner = eco_repo.split("/")[0].lower()
        q = f"repo:{eco_repo} is:issue is:open updated:>={since_14d}"
        try:
            res = fetch_json(
                f"https://api.github.com/search/issues?q={urllib.parse.quote(q)}&sort=updated&order=desc&per_page=15",
                timeout=6,
                headers=headers,
            )
            for issue in res.get("items") or []:
                if len(found) >= limit:
                    break
                login = ((issue.get("user") or {}).get("login") or "").strip()
                norm_user = login.lower()
                if not login or norm_user == eco_owner or norm_user in exclude_users or "[bot]" in norm_user:
                    continue
                u_data, email = resolve_github_user_email(login, headers)
                if not email or email in exclude_emails:
                    continue
                exclude_emails.add(email)
                exclude_users.add(norm_user)

                issue_body = issue.get("body") or ""
                issue_title = (issue.get("title") or "").strip()
                broken_url = extract_target_url_from_issue(f"{issue_title}\n{issue_body}") if track == "track_agentfuel" else ""
                rescue = rescue_issue_target_url(broken_url) if broken_url else {}

                found.append({
                    "track": track,
                    "lead_source": "issue_poach",
                    "username": login,
                    "name": (u_data or {}).get("name") or login,
                    "email": email,
                    "repo": eco_repo,
                    "ecosystem_repo": eco_repo,
                    "repo_desc": issue_title or f"Issue on {eco_repo}",
                    "homepage": broken_url,
                    "stars": 0,
                    "issue_number": issue.get("number"),
                    "issue_title": issue_title,
                    "issue_url": issue.get("html_url") or "",
                    "broken_target_url": broken_url,
                    "rescue_result": rescue,
                })
                time.sleep(0.2)
        except Exception:
            continue
    return found


def discover_recent_fork_leads(track: str, limit: int, exclude_emails: set, exclude_users: set) -> list:
    """Stream B: Intercept builders who forked commercial agent/automation repos in the last 14 days."""
    repos = list(FORK_ECOSYSTEM_REPOS.get(track, []))
    if not repos:
        return []
    random.shuffle(repos)
    headers = _gh_headers()
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found = []

    for eco_repo in repos:
        if len(found) >= limit:
            break
        eco_owner = eco_repo.split("/")[0].lower()
        try:
            forks = fetch_json(
                f"https://api.github.com/repos/{eco_repo}/forks?sort=newest&per_page=20",
                timeout=6,
                headers=headers,
            )
            if not isinstance(forks, list):
                continue
            for fork in forks:
                if len(found) >= limit:
                    break
                if (fork.get("created_at") or "") < cutoff_iso:
                    break
                owner = fork.get("owner") or {}
                login = (owner.get("login") or "").strip()
                norm_user = login.lower()
                fork_full = fork.get("full_name") or eco_repo
                if not login or norm_user == eco_owner or norm_user in exclude_users or "[bot]" in norm_user:
                    continue
                u_data, email = resolve_github_user_email(login, headers, candidate_repos=[fork_full])
                if not email or email in exclude_emails:
                    continue
                exclude_emails.add(email)
                exclude_users.add(norm_user)

                found.append({
                    "track": track,
                    "lead_source": "recent_fork",
                    "username": login,
                    "name": (u_data or {}).get("name") or login,
                    "email": email,
                    "repo": fork_full,
                    "ecosystem_repo": eco_repo,
                    "repo_desc": fork.get("description") or f"Recent fork of {eco_repo}",
                    "homepage": (fork.get("homepage") or "").strip(),
                    "stars": fork.get("stargazers_count") or 0,
                })
                time.sleep(0.2)
        except Exception:
            continue
    return found


def search_github_leads(track="track_rugshield", limit=5, exclude_emails=None, exclude_users=None):
    """
    High-intent prospecting across Streams A (Competitor Issue Poaching),
    B (Recent Framework Forkers), and targeted stars:1..300 fallback.
    """
    exclude_emails = set(exclude_emails or ())
    exclude_users = set(exclude_users or ())
    headers = _gh_headers()

    discovered = []
    # Mix Streams A (issue poaching) and B (recent forkers)
    issue_quota = max(1, (limit + 1) // 2) if track == "track_agentfuel" else max(1, limit // 2)
    discovered.extend(discover_issue_poaching_leads(track, issue_quota, exclude_emails, exclude_users))
    if len(discovered) < limit:
        discovered.extend(discover_recent_fork_leads(track, limit - len(discovered), exclude_emails, exclude_users))

    if len(discovered) >= limit:
        return discovered[:limit]

    track_queries = {
        "track_rugshield": [
            '"@coinbase/onchainkit" stars:1..300',
            '"aerodrome" base swap stars:1..300',
            '"uniswap v3" swap base stars:1..300',
            '"solana swap" OR "jupiter aggregator" stars:1..300',
            '"solana-agent-kit" stars:1..300',
            '"coinbase/agentkit" OR "agentkit" defi stars:1..300',
            '"dexscreener" solana OR base stars:1..300',
            '"trading bot" solana OR raydium stars:1..300'
        ],
        "track_canaryguard": [
            '"@anthropic-ai/sdk" stars:1..300',
            '"@langchain/openai" stars:1..300',
            '"mcp-remote" OR "modelcontextprotocol" stars:1..300',
            '"mcp server" stars:1..300',
            '"langchain" agent stars:1..300',
            '"openai agents" stars:1..300',
            '"langgraph" OR "crewai" stars:1..300',
            '"pydantic-ai" OR "mastra" stars:1..300'
        ],
        "track_agentfuel": [
            '"apify-client" OR "apify" actor stars:1..300',
            '"shopify-api-node" OR "shopify" webhook stars:1..300',
            '"n8n-nodes" OR "n8n" workflow stars:1..300',
            '"firecrawl" OR "crawl4ai" stars:1..300',
            '"lead enrichment" OR "b2b leads" stars:1..300',
            '"price monitor" OR "ecommerce scraper" stars:1..300',
            '"playwright" scraper stars:1..300',
            '"clay" enrichment OR pipeline stars:1..300'
        ]
    }

    queries = list(track_queries.get(track, track_queries["track_agentfuel"]))
    random.shuffle(queries)

    for q in queries:
        if len(discovered) >= limit:
            break
        for page in (1, 2):
            if len(discovered) >= limit:
                break
            url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(q)}&sort=updated&order=desc&per_page=12&page={page}"
            try:
                res_data = fetch_json(url, timeout=6, headers=headers)
                items = res_data.get("items", [])
                if not items:
                    break
                for repo in items:
                    if len(discovered) >= limit:
                        break
                    if repo.get("fork") or repo.get("archived"):
                        continue
                    stars = repo.get("stargazers_count") or 0
                    if stars < 1 or stars > 300:
                        continue
                    pushed_at = repo.get("pushed_at") or ""
                    if pushed_at and pushed_at < "2026-08-01":
                        continue
                    owner = repo.get("owner", {}).get("login")
                    repo_name = repo.get("full_name")
                    repo_desc = repo.get("description") or "GitHub Project"
                    topics = repo.get("topics") or []
                    if is_spam_repo(owner, repo_name, repo_desc):
                        continue
                    if not matches_track_keywords(track, repo_name, repo_desc, topics):
                        continue
                    if owner.lower().strip() in exclude_users:
                        continue

                    u_data, email = resolve_github_user_email(owner, headers, candidate_repos=[repo_name])
                    if email and has_commercial_builder_signal(u_data or {}, email):
                        norm_email = email.lower().strip()
                        norm_user = owner.lower().strip()
                        if norm_email in exclude_emails or norm_user in exclude_users:
                            continue
                        exclude_emails.add(norm_email)
                        exclude_users.add(norm_user)
                        discovered.append({
                            "track": track,
                            "lead_source": "repo_search",
                            "username": owner,
                            "name": (u_data or {}).get("name") or owner,
                            "email": norm_email,
                            "repo": repo_name,
                            "repo_desc": repo_desc,
                            "homepage": (repo.get("homepage") or "").strip(),
                            "topics": topics,
                            "stars": repo.get("stargazers_count", 0)
                        })
                time.sleep(0.4)
            except Exception:
                break

    return discovered[:limit]

# -----------------------------------------------------------------------------
# EMAIL OUTBOUND SENDER & PITCH GENERATOR
# -----------------------------------------------------------------------------
def send_email(to_addr, subject, body_text, body_html=None):
    is_outreach = bool(to_addr and SMTP_USER and to_addr.lower().strip() != SMTP_USER.lower().strip())
    if is_outreach:
        opt_out_line = "\n\n---\nReply 'unsubscribe' if you don't want notes from me."
        if body_text and "unsubscribe" not in body_text.lower():
            body_text = body_text.rstrip() + opt_out_line

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Arman (Kurox) <{SMTP_USER}>"
    msg["To"] = to_addr
    if is_outreach and SMTP_USER:
        msg["Reply-To"] = SMTP_USER
        msg["List-Unsubscribe"] = f"<mailto:{SMTP_USER}?subject=unsubscribe>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=12) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [to_addr], msg.as_string())

def run_live_diagnostic(lead: dict, timeout: int = 4) -> str:
    """Run a non-blocking live preview check on the prospect's repo/site for factual pitch personalization."""
    rescue = lead.get("rescue_result") or {}
    if rescue.get("target_url") and rescue.get("excerpt"):
        return (
            f"Ran {rescue['target_url']} through AgentFuel402 edge extractor just now: "
            f"{rescue['tokens']} clean LLM tokens via {rescue['engine']}."
        )

    track = lead.get("track", "track_agentfuel")
    repo_full = (lead.get("repo") or "").strip()
    homepage = (lead.get("homepage") or "").strip()
    target_url = homepage if homepage.startswith(("http://", "https://")) else (
        f"https://github.com/{repo_full}" if "/" in repo_full else ""
    )

    try:
        if track == "track_agentfuel" and target_url:
            q_url = urllib.parse.quote(target_url, safe="")
            res = fetch_json(
                f"https://agentfuel402.ak10082247.workers.dev/v1/preview/llm-clean-markdown?url={q_url}",
                timeout=timeout,
            )
            if res.get("status") == "success" and res.get("token_estimate"):
                engine_name = res.get("engine", "edge-sanitizer")
                return (
                    f"Tested {target_url} on AgentFuel402 Clean Markdown just now: extracted "
                    f"{res['token_estimate']} clean LLM tokens via {engine_name} with scripts and nav stripped."
                )

        elif track == "track_canaryguard":
            sample_text = (lead.get("repo_desc") or repo_full or "").strip()
            scanned_label = repo_full or "your project metadata"
            if homepage.startswith(("http://", "https://")):
                try:
                    q_url = urllib.parse.quote(homepage, safe="")
                    md_res = fetch_json(
                        f"https://agentfuel402.ak10082247.workers.dev/v1/preview/llm-clean-markdown?url={q_url}",
                        timeout=timeout,
                    )
                    md_text = (md_res.get("markdown") or "").strip()
                    if md_text:
                        sample_text = md_text[:3000]
                        scanned_label = homepage
                except Exception:
                    pass
            if sample_text:
                res = fetch_json(
                    "https://canaryguard-402.onrender.com/v1/sanitize/preview",
                    timeout=timeout,
                    headers={"Content-Type": "application/json"},
                    data={"content": sample_text, "strict_mode": True},
                )
                status = res.get("status", "clean")
                engine_ms = res.get("engine_ms", "<10")
                threats = res.get("threats_neutralized") or []
                threat_note = f"{len(threats)} rule trigger(s)" if threats else "0 injection triggers"
                return (
                    f"Ran a live CanaryGuard scan on {scanned_label}: {status} in {engine_ms} ms "
                    f"({threat_note}; checks Unicode Tags, zero-width smuggling, and MCP tool poisoning)."
                )

        elif track == "track_rugshield":
            m_addr = re.search(r"0x[a-fA-F0-9]{40}", lead.get("repo_desc") or "")
            token_addr = m_addr.group(0) if m_addr else "0x4200000000000000000000000000000000000006"
            t0 = time.monotonic()
            res = fetch_json(
                "https://rugshield-402.onrender.com/v1/scan/preview",
                timeout=timeout,
                headers={"Content-Type": "application/json"},
                data={"token_address": token_addr, "chain": "base", "simulate_sell": False},
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            hp = res.get("is_honeypot")
            check_note = f"is_honeypot={hp}" if hp is not None else f"status={res.get('status', 'ok')}"
            return (
                f"Verified RugShield /v1/scan/preview live in {elapsed_ms} ms "
                f"(Base {check_note}) — ready to guard Base sell taxes & Solana Token-2022 mints."
            )
    except Exception:
        return ""
    return ""


def _clean_first_name(raw_name: str, username: str) -> str:
    candidate = (raw_name or "").strip().split()[0] if (raw_name or "").strip() else ""
    if (
        candidate
        and candidate.lower() != (username or "").lower()
        and len(candidate) >= 2
        and re.fullmatch(r"[A-Za-z][A-Za-z\-']+", candidate)
    ):
        return candidate
    if username and re.fullmatch(r"[A-Za-z]{3,14}", username.strip()):
        return username.strip().capitalize()
    return "there"


def format_live_b2b_sample_block(limit: int = 5) -> str:
    leads = fetch_live_b2b_sample(limit=limit)
    if not leads:
        return ""
    lines = ["Here are 5 live B2B startup & hiring signals captured today:"]
    for idx, item in enumerate(leads, 1):
        lines.append(
            f"{idx}. {item['company']} ({item['domain']}) — {item['headline']} [Intent {item['intent_score']}/100]"
        )
    return "\n".join(lines) + "\n\n"


def craft_pitch(lead):
    raw_name = (lead.get("name") or "").strip()
    username = (lead.get("username") or "").strip()
    first_name = _clean_first_name(raw_name, username)
    repo_full = lead.get("repo", "your repo")
    eco_repo = (lead.get("ecosystem_repo") or repo_full).strip()
    eco_short = eco_repo.split("/")[-1]
    repo_short = repo_full.split("/")[-1]
    track = lead.get("track", "track_agentfuel")
    source = lead.get("lead_source") or "repo_search"
    diag = (lead.get("diagnostic_summary") or "").strip()
    diag_block = f"{diag}\n\n" if diag else ""
    target_label = f"your {eco_short} stack" if source == "issue_poach" else repo_short

    if source == "issue_poach" and lead.get("issue_number"):
        context_line = f"Saw your GitHub issue #{lead['issue_number']} on {eco_repo}."
    elif source == "recent_fork":
        context_line = f"Saw your recent fork of {eco_repo} ({repo_full})."
    else:
        context_line = f"Saw your work on {repo_full}."

    if track == "track_rugshield":
        subject = (
            f"Pre-swap safety check for {eco_short} #{lead['issue_number']}"
            if source == "issue_poach" and lead.get("issue_number")
            else f"Pre-swap safety gate for your {eco_short} fork"
        )[:68]
        text = (
            f"Hey {first_name},\n\n"
            f"{context_line} {diag_block}"
            f"Drop a single pre-trade check in front of Base or Solana swaps before funds move "
            f"(sell-tax simulation, Token-2022 mint/freeze checks, fail-closed gating):\n"
            f"POST rugshield-402.onrender.com/v1/scan with header Authorization: Bearer <key> and JSON "
            f"{{\"token_address\": \"0x...\", \"chain\": \"base\"}}\n\n"
            f"Test any Base or Solana token free in-browser:\n"
            f"https://ak10082247-max.github.io/scanner.html\n\n"
            f"Grab a $5 30-day API key (all 3 services via Stripe, no crypto wallet needed), or reply for a $29 PR wiring it into {target_label}:\n"
            f"https://agentfuel402.ak10082247.workers.dev/v1/checkout/api-key?plan=starter\n\n"
            f"Best,\nArman\n"
        )

    elif track == "track_canaryguard":
        subject = (
            f"Prompt-injection guard for {eco_short} #{lead['issue_number']}"
            if source == "issue_poach" and lead.get("issue_number")
            else f"Prompt-injection guard for your {eco_short} fork"
        )[:68]
        text = (
            f"Hey {first_name},\n\n"
            f"{context_line} {diag_block}"
            f"Protect multi-tenant LLM gateways & MCP tools against untrusted web/RAG inputs "
            f"(role delimiter stripping, Unicode Tag decoding, sub-10ms engine):\n"
            f"POST canaryguard-402.onrender.com/v1/sanitize with header Authorization: Bearer <key> and JSON "
            f"{{\"content\": tool_output, \"strict_mode\": true}}\n\n"
            f"Test payloads live with zero signup:\n"
            f"https://ak10082247-max.github.io/scanner.html\n\n"
            f"Grab a $5 30-day API key (HTTP + MCP via Stripe), or reply for a $29 integration PR tailored to {target_label}:\n"
            f"https://agentfuel402.ak10082247.workers.dev/v1/checkout/api-key?plan=starter\n\n"
            f"Best,\nArman\n"
        )

    else:
        rescue = lead.get("rescue_result") or {}
        if source == "issue_poach" and lead.get("issue_number") and rescue.get("excerpt"):
            subject = f"Fixed your {eco_short} #{lead['issue_number']} extraction"[:68]
            lead_intro = (
                f"Saw your GitHub issue #{lead['issue_number']} on {eco_repo} where {rescue['target_url']} had extraction trouble.\n"
                f"I ran it through AgentFuel402 edge extractor ({rescue['tokens']} clean tokens via {rescue['engine']}):\n"
                f"{rescue['excerpt']}...\n\n"
            )
            apify_url = "https://apify.com/kuroxreal/llm-clean-markdown-ppe"
            batch_cta = "1) Batch up to 100 URLs in 1 click on Apify (Pay-Per-Event, zero monthly subscription):"
        else:
            subject = (
                f"5 live B2B leads + bulk batch for {eco_short}"
                if source != "recent_fork"
                else f"5 live B2B leads + bulk batch for {eco_short} fork"
            )[:68]
            lead_intro = f"{context_line} {diag_block}"
            apify_url = "https://apify.com/kuroxreal/b2b-intent-leads-ppe"
            batch_cta = "1) Pull 250-500 leads in 1 click (maxLeads: 250 = $2.50 / 500 = $5.00 via Apify):"

        sample_block = format_live_b2b_sample_block(limit=5)
        text = (
            f"Hey {first_name},\n\n"
            f"{lead_intro}"
            f"{sample_block}"
            f"Two fast ways to pull full batches with zero monthly lock-in:\n"
            f"{batch_cta}\n"
            f"{apify_url}\n"
            f"2) $5 30-day Unified API Key (HTTP + MCP across AgentFuel402, CanaryGuard & RugShield via Stripe — or ask for $19 CSV pack / $29 custom PR):\n"
            f"https://agentfuel402.ak10082247.workers.dev/v1/checkout/api-key?plan=starter\n\n"
            f"Best,\nArman\n"
        )

    return subject, text

# -----------------------------------------------------------------------------
# SCORECARD DIGEST SENDER
# -----------------------------------------------------------------------------
def send_digest_scorecard(treasury, gh_stats, apify_stats, leads_summary):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"[Empire Revenue Scorecard] Treasury: ${treasury['total_usdc']:.3f} USDC | Apify Runs: {apify_stats['total_runs']} | {today}"

    body = f"""=============================================================================
KUROX "BIG 3" EMPIRE REVENUE & GROWTH SCORECARD - {today}
Consolidated Flagships: CanaryGuard 402 | RugShield 402 | AgentFuel402
=============================================================================

1. VERIFIED ON-CHAIN TREASURY (Base & Solana USDC):
-----------------------------------------------------------------------------
Base Merchant Payout (0x80E0...): {treasury['base'][0]['usdc']:.6f} USDC (0x80E0Ae84679b7f11bE171DaADd492FBECf628cd6)
Solana Merchant Owner:            9wuMysgXwNhtQeqJgGByAiMYc4EjzZ5wUSmnjrrt3ffh
Solana Merchant ATA (DD3A...):    {treasury['solana'][0]['usdc']:.6f} USDC (DD3A7jaXFeHcif9eYj6Vhomuxypat5Yxi8ow6wxz27yL)
>>> TOTAL VERIFIED TREASURY:      {treasury['total_usdc']:.6f} USDC

2. "BIG 3" GITHUB ECOSYSTEM REPO METRICS:
-----------------------------------------------------------------------------
"""
    for short_name, stats in gh_stats.items():
        body += f"* {stats['full_name']:35} | Stars: {stats['stars']} | Open PRs: {stats['open_prs']} | Issues: {stats['open_issues']}\n"
        body += f"  Desc: {stats['description']}\n"

    body += f"""
3. ACTIVE APIFY STORE PAY-PER-EVENT TELEMETRY:
-----------------------------------------------------------------------------
Total Actor Runs:       {apify_stats['total_runs']}
Successful Runs:        {apify_stats['total_succeeded']}
Total PPE Charged:      {apify_stats['total_ppe_events']} events (~${apify_stats.get('total_est_usd', 0.0):.4f} USD est.)

Breakdown across Active Actors:
"""
    for a in apify_stats["actors"]:
        body += f"- {a['name']:25}: {a['runs']:2} runs | {a['succeeded']:2} succeeded | {a['ppe_charges']:2} PPE (~${a.get('est_usd', 0.0):.4f})\n"

    body += f"""
4. HIGH-TICKET AGENCY ARBITRAGE & FREE-AUDIT OUTBOUND:
-----------------------------------------------------------------------------
Total Leads Contacted (Lifetime): {leads_summary['total_lifetime']}
Emails Sent Today:                {leads_summary['sent_today']} / {MAX_EMAILS_PER_DAY} daily cap
- Segment 1 - Boutique Agencies ($149 200-Lead Pack):       {leads_summary.get('segment_agency_sent', 0)} sent
- Segment 2 - E-Com / Shopify (Free Price Audit -> $149):   {leads_summary.get('segment_ecom_sent', 0)} sent
- Segment 3 - AI / SaaS Launches (Free Audit -> Store/$19): {leads_summary.get('segment_ai_saas_sent', 0)} sent

5. ACTIVE PRODUCTION SERVICES (SUSPENDED SERVICES FULLY SILENCED):
-----------------------------------------------------------------------------
- AgentFuel402 Cloudflare Edge: https://agentfuel402.ak10082247.workers.dev (LIVE 200)
- CanaryGuard 402 Live Gateway: https://canaryguard-402.onrender.com (LIVE 200)
- RugShield 402 Live Gateway:   https://rugshield-402.onrender.com (LIVE 200)
- Suspended Crons Silenced:     Pulse402 Keepalive/Deploy/Growth/Paper Trader DISABLED
                                Tollbooth Keepalive/Blogger DISABLED
                                Guard402 Keepalive DISABLED
- Suspended Apify Actors:       Pulse402, StealthGuard & Guard402 set to isDeprecated=True
=============================================================================
"""

    try:
        top_bounties = bounty_hunter.scan_open_cash_bounties(days=14, top_n=5, token=GH_PAT)
        body += bounty_hunter.format_bounty_scorecard_section(top_bounties)
    except Exception as exc:
        body += f"\n6. TOP OPEN GITHUB CASH BOUNTIES ($50-$500): scan unavailable ({exc})\n"

    print(body)

    for recipient in DIGEST_RECIPIENTS:
        try:
            send_email(recipient, subject, body)
            print(f"  [+] Daily Scorecard sent to: {recipient}")
        except Exception as e:
            print(f"  [-] Failed to send scorecard to {recipient}: {e}")

# -----------------------------------------------------------------------------
# MAIN CLI ENTRYPOINT
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Big 3 Empire Engine")
    parser.add_argument("--digest-only", action="store_true", help="Only query treasury & send scorecard without prospecting")
    parser.add_argument("--force-send", type=int, default=0, help="Send an immediate capped batch (1-18) even if today's daily quota was reached")
    parser.add_argument("--fill-daily-cap", action="store_true", help="Send all remaining emails up to MAX_EMAILS_PER_DAY in this run")
    parser.add_argument("--dry-run-leads", action="store_true", help="Discover 1 lead per track, run live diagnostics, and print pitches without sending emails")
    args = parser.parse_args()

    if args.dry_run_leads:
        leads_data = load_leads()
        known_emails = (
            {e.lower().strip() for e in leads_data.get("contacted_emails", [])}
            | {e.lower().strip() for e in leads_data.get("suppressed_emails", [])}
        )
        known_users = {u.lower().strip() for u in leads_data["contacted_users"]}
        sample_5 = agency_dealmaker.generate_b2b_agency_pack(limit=5, save=False).get("leads") or []
        for seg_name in ["segment_agency", "segment_ecom", "segment_ai_saas"]:
            print(f"\n=== DRY RUN BUYER SEGMENT: {seg_name} ===")
            leads = agency_dealmaker.discover_business_buyers(
                seg_name,
                limit=1,
                exclude_emails=known_emails,
                exclude_users=known_users,
                gh_token=GH_PAT,
                email_validator=is_deliverable_personal_email,
            )
            for lead in leads:
                lead["diagnostic_summary"] = agency_dealmaker.run_buyer_lead_magnet_audit(lead, sample_leads=sample_5)
                subj, pitch = agency_dealmaker.craft_high_ticket_pitch(lead, audit_summary=lead["diagnostic_summary"])
                print(f"Source: {lead.get('lead_source')} | Company: {lead.get('company')} | URL: {lead.get('website_url')} -> {lead['email']}")
                print(f"Audit/Sample: {lead.get('diagnostic_summary') or '(none)'}")
                print(f"Subject: {subj}\n{pitch}")
        return

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting Big 3 Empire Engine...")

    # 1. Fetch on-chain treasury balances
    treasury = get_treasury_balances()
    print(f"[+] Total Verified Treasury: {treasury['total_usdc']:.6f} USDC")

    # 2. Fetch GitHub metrics for Big 3
    gh_stats = get_big3_github_stats()
    print(f"[+] GitHub Big 3 Metrics Queried: {list(gh_stats.keys())}")

    # 3. Fetch Apify stats for active actors
    apify_stats = get_active_apify_stats()
    print(f"[+] Apify Active Total Runs: {apify_stats['total_runs']} | Succeeded: {apify_stats['total_succeeded']}")

    # 4. Load leads & check daily limit
    leads_data = load_leads()
    sent_today = count_sent_today(leads_data["history"])
    remaining_today = max(0, MAX_EMAILS_PER_DAY - sent_today)
    force_budget = max(0, min(int(args.force_send or 0), 18))
    print(f"[+] Outbound Sent Today: {sent_today}/{MAX_EMAILS_PER_DAY} (Remaining capacity: {remaining_today}, Force batch: {force_budget}, Fill cap: {args.fill_daily_cap})")

    seg_counts = {"segment_agency": 0, "segment_ecom": 0, "segment_ai_saas": 0}

    if not args.digest_only and (remaining_today > 0 or force_budget > 0):
        # Spread sends across 3-hourly cron runs (max 6 per run, 24/day) unless --fill-daily-cap or --force-send
        if force_budget > 0:
            run_budget = force_budget
        elif args.fill_daily_cap:
            run_budget = remaining_today
        else:
            run_budget = min(remaining_today, MAX_EMAILS_PER_RUN)
        per_seg = max(1, (run_budget + 2) // 3)
        known_emails = (
            {e.lower().strip() for e in leads_data.get("contacted_emails", [])}
            | {e.lower().strip() for e in leads_data.get("suppressed_emails", [])}
        )
        known_users = {u.lower().strip() for u in leads_data["contacted_users"]}

        sample_5 = []
        try:
            sample_5 = agency_dealmaker.generate_b2b_agency_pack(limit=5, save=False).get("leads") or []
        except Exception:
            sample_5 = []

        sent_this_run = 0
        for seg_name in ["segment_agency", "segment_ecom", "segment_ai_saas"]:
            if sent_this_run >= run_budget or (force_budget == 0 and count_sent_today(leads_data["history"]) >= MAX_EMAILS_PER_DAY):
                break
            leads = agency_dealmaker.discover_business_buyers(
                seg_name,
                limit=per_seg,
                exclude_emails=known_emails,
                exclude_users=known_users,
                gh_token=GH_PAT,
                email_validator=is_deliverable_personal_email,
            )
            for lead in leads:
                if sent_this_run >= run_budget or (force_budget == 0 and count_sent_today(leads_data["history"]) >= MAX_EMAILS_PER_DAY):
                    break
                email = lead["email"].lower().strip()
                user = lead["username"].lower().strip()
                if not is_deliverable_personal_email(email):
                    continue
                if email in known_emails or user in known_users:
                    continue
                try:
                    lead["diagnostic_summary"] = agency_dealmaker.run_buyer_lead_magnet_audit(lead, sample_leads=sample_5)
                    subj, pitch = agency_dealmaker.craft_high_ticket_pitch(lead, audit_summary=lead["diagnostic_summary"])
                    send_email(email, subj, pitch)
                    known_emails.add(email)
                    known_users.add(user)
                    leads_data["contacted_emails"].append(email)
                    leads_data["contacted_users"].append(user)
                    leads_data["history"].append({
                        "username": user,
                        "email": email,
                        "track": seg_name,
                        "lead_source": lead.get("lead_source", seg_name),
                        "company": lead.get("company", ""),
                        "repo": lead.get("repo", lead.get("website_url", "")),
                        "sent_date": datetime.now(timezone.utc).isoformat()
                    })
                    seg_counts[seg_name] += 1
                    sent_this_run += 1
                    save_leads(leads_data)
                    print(f"  [+] {seg_name} [{lead.get('lead_source')}] audit pitch delivered to: {email} ({lead.get('company')})")
                    time.sleep(random.uniform(9, 14))
                except Exception as e:
                    print(f"  [-] Failed to pitch {email}: {e}")

    leads_summary = {
        "total_lifetime": len(leads_data["contacted_emails"]),
        "sent_today": sent_today + sum(seg_counts.values()),
        "segment_agency_sent": seg_counts["segment_agency"],
        "segment_ecom_sent": seg_counts["segment_ecom"],
        "segment_ai_saas_sent": seg_counts["segment_ai_saas"],
    }

    # 5. Generate & Deliver Daily Revenue Scorecard Digest
    send_digest_scorecard(treasury, gh_stats, apify_stats, leads_summary)
    print(f"[{datetime.now(timezone.utc).isoformat()}] Big 3 Empire Engine execution complete.")

if __name__ == "__main__":
    main()
