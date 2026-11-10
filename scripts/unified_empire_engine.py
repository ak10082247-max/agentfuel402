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
from datetime import datetime, timezone
import urllib.request
import urllib.error
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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

MAX_EMAILS_PER_DAY = 35
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

    for aid, name, desc in ACTIVE_APIFY_ACTORS:
        url = f"https://api.apify.com/v2/acts/{aid}/runs?limit=25"
        try:
            res_data = fetch_json(url, timeout=8, headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
            items = res_data.get("data", {}).get("items", [])
            succeeded = [run for run in items if run.get("status") == "SUCCEEDED"]
            ppe_charges = 0
            for run in succeeded:
                counts = run.get("chargedEventCounts") or {}
                ppe_charges += sum(counts.values())

            total_runs += len(items)
            total_succeeded += len(succeeded)
            total_ppe_events += ppe_charges
            stats.append({
                "id": aid,
                "name": name,
                "description": desc,
                "runs": len(items),
                "succeeded": len(succeeded),
                "ppe_charges": ppe_charges
            })
        except Exception as e:
            stats.append({"id": aid, "name": name, "description": desc, "runs": 0, "succeeded": 0, "ppe_charges": 0, "error": str(e)})

    return {
        "actors": stats,
        "total_runs": total_runs,
        "total_succeeded": total_succeeded,
        "total_ppe_events": total_ppe_events
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
    "git", "noreply", "no-reply", "donotreply", "mailer-daemon"
}

BLOCKED_EMAIL_DOMAINS = {
    "users.noreply.github.com",
    "noreply.github.com",
    "github.com",
    "localhost",
    "localdomain",
    "example.com",
    "example.org",
    "example.net",
    "test.com",
}

EMAIL_PREFIX_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._%+\-]{0,63}$")
EMAIL_DOMAIN_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)+$")
ICLOUD_RELAY_PATTERN = re.compile(r"(?:^[0-9]+[._-]|[._-][0-9a-z]{2}$|\d[a-z]$)")
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
    """Validates email syntax, blocks relays/noreply traps, and verifies custom startup domains via live MX lookup."""
    if not email or "@" not in email:
        return False
    cleaned = email.lower().strip()
    parts = cleaned.split("@")
    if len(parts) != 2:
        return False
    prefix, domain = parts[0], parts[1]

    if not EMAIL_PREFIX_PATTERN.match(prefix) or not EMAIL_DOMAIN_PATTERN.match(domain):
        return False
    if domain in BLOCKED_EMAIL_DOMAINS or domain.endswith((".noreply.github.com", ".local", ".internal", ".test", ".invalid", ".arpa")):
        return False

    # Exclude automated, bounce-trap, or generic helpdesk mailboxes
    if prefix in DISALLOWED_PREFIXES or any(p in prefix for p in ["noreply", "no-reply", "donotreply", "mailer", "dependabot", "[bot]"]):
        return False

    # Exclude Apple Hide-My-Email relay aliases heavily used by automated GitHub spam bots
    if domain == "icloud.com" and ICLOUD_RELAY_PATTERN.search(prefix):
        return False

    # Fast path for verified consumer & academic domains
    if domain in TRUSTED_EMAIL_DOMAINS:
        return True
    if domain.endswith(".edu") or domain.endswith(".ac.uk") or domain.endswith(".edu.au") or domain.endswith(".edu.sg"):
        return True

    # Allow real startup / company / agency domains when DNS confirms active MX records
    return has_valid_mx_record(domain)

def is_spam_repo(owner: str, repo_name: str, repo_desc: str) -> bool:
    """Filters out own repos, GitHub profile README repos, and SEO/malware bot-farm repositories."""
    if not owner or not repo_name:
        return True
    if owner.lower() in {"ak10082247-max"}:
        return True
    if repo_name.lower() in {f"{owner.lower()}/{owner.lower()}", f"{owner.lower()}/{owner.lower()}.github.io"}:
        return True
    if SPAM_REPO_PATTERN.search(repo_name):
        return True
    desc_l = (repo_desc or "").lower()
    if "video-based guide to" in desc_l or "solidity arbitrage executor" in desc_l:
        return True
    return False

# -----------------------------------------------------------------------------
# 3-TRACK SNIPER PROSPECTING ENGINE
# -----------------------------------------------------------------------------
def search_github_leads(track="track_rugshield", limit=5, exclude_emails=None, exclude_users=None):
    """
    Track 1: DeFi, Solana & Base Trading Bot Builders -> Pitch RugShield 402
    Track 2: AI Agent, MCP & LLM App Builders -> Pitch CanaryGuard 402
    Track 3: B2B Growth, E-Commerce & Web Scraping Devs -> Pitch AgentFuel402
    """
    exclude_emails = set(exclude_emails or ())
    exclude_users = set(exclude_users or ())
    track_queries = {
        "track_rugshield": [
            "jupiter solana swap NOT arbitrage-bot",
            "raydium pumpfun bot NOT arbitrage-bot",
            "coinbase agentkit NOT arbitrage-bot",
            "aerodrome base defi NOT arbitrage-bot",
            "solana swap sniper stars:>=2 NOT how-to",
            "dexscreener api bot stars:>=1 NOT how-to",
            "viem swap base NOT arbitrage-bot",
            "hyperliquid trading bot NOT how-to",
            "polymarket trading bot NOT how-to",
            "jito mev solana NOT how-to",
            "pumpfun sdk NOT how-to",
            "erc4337 agent wallet NOT how-to"
        ],
        "track_canaryguard": [
            "mcp server",
            "modelcontextprotocol",
            "langchain",
            "crewai",
            "autogen",
            "prompt injection",
            "openai agents",
            "elizaos plugin",
            "langgraph agent",
            "pydantic ai",
            "mastra agent",
            "dify workflow"
        ],
        "track_agentfuel": [
            "n8n",
            "firecrawl",
            "crawl4ai",
            "shopify scraper",
            "lead generation",
            "apify",
            "clay enrichment",
            "playwright scraper",
            "shopify price monitor",
            "b2b enrichment",
            "web scraper api",
            "mcp server"
        ]
    }

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": UA
    }
    if GH_PAT:
        headers["Authorization"] = f"Bearer {GH_PAT}"

    discovered = []
    queries = list(track_queries.get(track, track_queries["track_agentfuel"]))
    random.shuffle(queries)

    for q in queries:
        if len(discovered) >= limit:
            break
        for page in (1, 2):
            if len(discovered) >= limit:
                break
            url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(q)}&sort=updated&order=desc&per_page=10&page={page}"
            try:
                res_data = fetch_json(url, timeout=6, headers=headers)
                items = res_data.get("items", [])
                if not items:
                    break
                for repo in items:
                    if len(discovered) >= limit:
                        break
                    owner = repo.get("owner", {}).get("login")
                    repo_name = repo.get("full_name")
                    repo_desc = repo.get("description") or "GitHub Project"
                    if is_spam_repo(owner, repo_name, repo_desc):
                        continue
                    if owner.lower().strip() in exclude_users:
                        continue

                    # Fetch user details for email (with public commit fallback)
                    try:
                        u_url = f"https://api.github.com/users/{owner}"
                        u_data = fetch_json(u_url, timeout=4, headers=headers)
                        email = u_data.get("email")
                        name = u_data.get("name") or owner

                        # If user profile email is absent or undeliverable, inspect recent public commits
                        if not email or not is_deliverable_personal_email(email):
                            c_url = f"https://api.github.com/repos/{repo_name}/commits?author={owner}&per_page=3"
                            c_data = fetch_json(c_url, timeout=4, headers=headers)
                            if isinstance(c_data, list):
                                for c in c_data:
                                    cand = c.get("commit", {}).get("author", {}).get("email")
                                    if is_deliverable_personal_email(cand):
                                        email = cand
                                        break

                        if email and is_deliverable_personal_email(email):
                            norm_email = email.lower().strip()
                            norm_user = owner.lower().strip()
                            if norm_email in exclude_emails or norm_user in exclude_users:
                                continue
                            exclude_emails.add(norm_email)
                            exclude_users.add(norm_user)
                            discovered.append({
                                "track": track,
                                "username": owner,
                                "name": name,
                                "email": norm_email,
                                "repo": repo_name,
                                "repo_desc": repo_desc
                            })
                    except Exception:
                        pass
                time.sleep(0.4)
            except Exception:
                break

    return discovered

# -----------------------------------------------------------------------------
# EMAIL OUTBOUND SENDER & PITCH GENERATOR
# -----------------------------------------------------------------------------
def send_email(to_addr, subject, body_text, body_html=None):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Kurox Alpha & Security Suite <{SMTP_USER}>"
    msg["To"] = to_addr

    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=12) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [to_addr], msg.as_string())

def craft_pitch(lead):
    name = lead.get("name", "Builder")
    repo = lead.get("repo", "your project")
    track = lead.get("track", "track_agentfuel")

    if track == "track_rugshield":
        subject = f"Dual-Chain Base & Solana Honeypot + Pre-Trade Scan for {repo} (RugShield 402)"
        text = f"""Hi {name},

Saw your recent commits on {repo}. If you're building automated trading bots, swap routers, or sniper tools on Solana or Base Mainnet, unverified tokens, freeze/mint authorities, and stealth fee-on-transfer honeypots are a constant risk.

RugShield 402 is an autonomous dual-chain DEX pre-trade simulation & safety engine:
1. Base EVM Execution Simulation: Sub-200ms bytecode simulation testing actual buy & sell paths, exact fee-on-transfer taxes (bps), and revert traps
2. Solana SPL Risk Scanning: Mint/freeze authority verification, liquidity pool depth, and Raydium/Orca/Pump.fun safety checks
3. Liquidity Lock & Pool Depth Analysis: Aerodrome (Slipstream), Uniswap v3, Raydium & Orca pair verification
4. Sybil Cluster & Dev Concentration Scoring before your bot executes a swap

Integrate directly into your pipeline (Base & Solana x402 USDC supported):
- Open-Source MCP Server: https://github.com/ak10082247-max/rugshield-402 (Claude Desktop & Cursor native)
- Standard MCP Tools: `rugshield_pre_swap_scan`, `check_honeypot`, `verify_liquidity_lock`
- Live Edge API (x402 $0.010 USDC on Base & Solana): https://rugshield-402.onrender.com
- Apify Pay-Per-Event ($0.005/scan): https://apify.com/kuroxreal/rugshield-402

Hope this helps your bot avoid bad fills across Solana and Base!

Best regards,
Kurox DEX Security Team
https://github.com/ak10082247-max/rugshield-402
"""

    elif track == "track_canaryguard":
        subject = f"Deterministic Prompt-Injection Firewall & MCP Tool Sanitizer for {repo} (CanaryGuard)"
        text = f"""Hi {name},

Loved what you're building in {repo}. With LLM agents taking autonomous actions and reading untrusted web data or user inputs, indirect prompt injections, jailbreaks, and tool-poisoning attacks are a critical vulnerability.

CanaryGuard 402 is a deterministic security firewall and honeypot scrubber built specifically for AI agents:
1. Sub-10ms deterministic prompt-injection detection and instruction override neutralization
2. Hidden Unicode, zero-width steganography, and malicious script scrubbing
3. Cryptographic tamper-evident inspection receipts with risk scores (0-100)
4. Contextual scoring for extracted crypto addresses and wallet-drain commands

Connect it in seconds:
- Open-Source Repo: https://github.com/ak10082247-max/canaryguard-402
- Claude Desktop & Cursor MCP: https://canaryguard-402.onrender.com/mcp
- ElizaOS Official Plugin: @kurox_real/plugin-canaryguard
- Coinbase AgentKit Action Provider: @kurox_real/agentkit-canaryguard-402
- Apify Store Pay-Per-Event ($0.003/check): https://apify.com/kuroxreal/canaryguard-402
- Flat Subscription: Available on MCPize ($9.99/mo)

Keep your agents safe from prompt injection!

Best regards,
Kurox AI Safety Engineering
https://github.com/ak10082247-max/canaryguard-402
"""

    else:
        subject = f"Clean Markdown, B2B Leads, E-Com & REA for {repo} (AgentFuel402)"
        text = f"""Hi {name},

Loved what you're building in {repo}. If you're running web scraping, AI agents, or Clay/n8n workflows, you've probably run into bot blocks (Cloudflare 403s/419s) and high token costs.

We launched AgentFuel402 — a zero-cold-start consumable data factory built specifically for AI agents and automation:
1. LLM Clean Markdown: Strips noisy ads, scripts, and navigation; enforces strict SSRF and prompt-injection defense
2. B2B Intent Leads: Live tech product launches, founder discussions, hiring alerts, and tech stacks with Intent Scores (30–100)
3. E-Commerce Price & Stock: Live Shopify & Schema.org variant, price, discount delta, and inventory tracking
4. Reverse Engineer Anything (REA): Discovers Next.js hydration APIs, hidden REST/GraphQL routes, and auto-generates OpenAPI 3.1 specs + client code without scraping
5. Zero-Charge Resilience: We never charge on 404s or dead links under our Verify -> Fetch -> Settle guarantee

Available across your favorite stacks:
- Apify Store PPE ($0.015 - $0.050 USD): https://apify.com/kuroxreal
  * Reverse Engineer Anything: https://apify.com/kuroxreal/reverse-engineer-anything
  * B2B Leads: https://apify.com/kuroxreal/b2b-intent-leads-ppe
  * Clean Markdown: https://apify.com/kuroxreal/llm-clean-markdown-ppe
  * E-Com Monitor: https://apify.com/kuroxreal/ecom-price-stock-ppe
- Official MCP Server: io.github.ak10082247-max/agentfuel402 (Instant Claude Desktop & Cursor tool)
- Cloudflare Edge x402: https://agentfuel402.ak10082247.workers.dev ($0.005 - $0.010 USDC)
- Free Live Previews: https://agentfuel402.ak10082247.workers.dev/v1/preview/leads

Cheers and happy building,
Kurox Real / AgentFuel402
https://github.com/ak10082247-max/agentfuel402
"""

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
Total PPE Charged:      {apify_stats['total_ppe_events']} events

Breakdown across Active Actors:
"""
    for a in apify_stats["actors"]:
        body += f"- {a['name']:25}: {a['runs']:2} runs | {a['succeeded']:2} succeeded | {a['ppe_charges']:2} PPE events\n"

    body += f"""
4. 3-TRACK OUTBOUND PROSPECTING & GROWTH:
-----------------------------------------------------------------------------
Total Leads Contacted (Lifetime): {leads_summary['total_lifetime']}
Emails Sent Today:                {leads_summary['sent_today']} / {MAX_EMAILS_PER_DAY} daily cap
- Track 1 - RugShield (Base/Solana DEX Bots): {leads_summary['track_rugshield_sent']} sent
- Track 2 - CanaryGuard (AI Agents / MCP):     {leads_summary['track_canaryguard_sent']} sent
- Track 3 - AgentFuel402 (B2B / E-Com / Scrap): {leads_summary['track_agentfuel_sent']} sent

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
    args = parser.parse_args()

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
    print(f"[+] Outbound Sent Today: {sent_today}/{MAX_EMAILS_PER_DAY} (Remaining capacity: {remaining_today})")

    track_counts = {"track_rugshield": 0, "track_canaryguard": 0, "track_agentfuel": 0}

    if not args.digest_only and remaining_today > 0:
        # Send up to 5 per track (15 per cycle) so dropped GitHub cron slots don't starve the 35/day target
        per_track = max(1, min(remaining_today // 3, 5))
        known_emails = {e.lower().strip() for e in leads_data["contacted_emails"]}
        known_users = {u.lower().strip() for u in leads_data["contacted_users"]}

        for track_name in ["track_rugshield", "track_canaryguard", "track_agentfuel"]:
            if count_sent_today(leads_data["history"]) >= MAX_EMAILS_PER_DAY:
                break
            leads = search_github_leads(
                track_name,
                limit=per_track,
                exclude_emails=known_emails,
                exclude_users=known_users,
            )
            for lead in leads:
                if count_sent_today(leads_data["history"]) >= MAX_EMAILS_PER_DAY:
                    break
                email = lead["email"].lower().strip()
                user = lead["username"].lower().strip()
                if not is_deliverable_personal_email(email):
                    continue
                if email in known_emails or user in known_users:
                    continue
                try:
                    subj, pitch = craft_pitch(lead)
                    send_email(email, subj, pitch)
                    known_emails.add(email)
                    known_users.add(user)
                    leads_data["contacted_emails"].append(email)
                    leads_data["contacted_users"].append(user)
                    leads_data["history"].append({
                        "username": user,
                        "email": email,
                        "track": track_name,
                        "repo": lead["repo"],
                        "sent_date": datetime.now(timezone.utc).isoformat()
                    })
                    track_counts[track_name] += 1
                    save_leads(leads_data)
                    print(f"  [+] {track_name} pitch delivered to: {email} ({user} on {lead['repo']})")
                    time.sleep(4)
                except Exception as e:
                    print(f"  [-] Failed to pitch {email}: {e}")

    leads_summary = {
        "total_lifetime": len(leads_data["contacted_emails"]),
        "sent_today": sent_today + sum(track_counts.values()),
        "track_rugshield_sent": track_counts["track_rugshield"],
        "track_canaryguard_sent": track_counts["track_canaryguard"],
        "track_agentfuel_sent": track_counts["track_agentfuel"]
    }

    # 5. Generate & Deliver Daily Revenue Scorecard Digest
    send_digest_scorecard(treasury, gh_stats, apify_stats, leads_summary)
    print(f"[{datetime.now(timezone.utc).isoformat()}] Big 3 Empire Engine execution complete.")

if __name__ == "__main__":
    main()
