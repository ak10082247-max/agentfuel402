#!/usr/bin/env python3
"""
Daily Store Data Compiler for AgentFuel402 (/store)
Compiles live, verified datasets with zero synthetic/placeholder rows:
  1. data/latest_base_alpha.json  - Fresh Base Mainnet & Solana token launches + DEX liquidity + GoPlus/RugCheck security
  2. data/latest_b2b_leads.json   - Up to 500 fresh AI/SaaS startups, Show HN launches, hiring orgs & GitHub builders
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import html
import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
DATA_DIR = os.path.join(REPO_ROOT, "data")
BASE_ALPHA_PATH = os.path.join(DATA_DIR, "latest_base_alpha.json")
B2B_LEADS_PATH = os.path.join(DATA_DIR, "latest_b2b_leads.json")
STORE_SNAPSHOTS_JS_PATH = os.path.join(DATA_DIR, "store_snapshots.js")

UA = "AgentFuel402-StoreCompiler/1.0 (+https://agentfuel402.ak10082247.workers.dev/store)"
ZW_RE = re.compile(r"[\u2000-\u200F\u202A-\u202F\uFEFF]+")
EMAIL_RE = re.compile(r"\b([A-Za-z0-9][A-Za-z0-9._%+\-]{0,63}@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)\b")
BLOCKED_EMAIL_DOMAINS = {
    "users.noreply.github.com",
    "noreply.github.com",
    "example.com",
    "example.org",
    "localhost",
}

QUOTE_BASE_TOKENS = {
    "0x4200000000000000000000000000000000000006",  # WETH
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC
    "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca",  # USDbC
    "0x50c5725949a6f0c72e6c4a641f24049a917db0cb",  # DAI
    "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",  # cbBTC
}
QUOTE_SOL_MINTS = {
    "So11111111111111111111111111111111111111112",   # wSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}

try:
    SSL_CTX = ssl._create_unverified_context()
except Exception:
    SSL_CTX = None


def resolve_gh_token() -> str:
    token = (os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PAT") or "").strip()
    if token:
        return token
    try:
        out = subprocess.check_output(["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL).strip()
        if out.startswith(("gh", "github_pat_")):
            return out
    except Exception:
        pass
    return ""


def fetch_json(url: str, timeout: int = 12, headers: dict | None = None):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    kwargs = {"timeout": timeout}
    if SSL_CTX is not None:
        kwargs["context"] = SSL_CTX
    with urllib.request.urlopen(req, **kwargs) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val, default: int = 0) -> int:
    try:
        if val is None or val == "":
            return default
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _clean_text(val: str) -> str:
    txt = html.unescape(str(val or ""))
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = ZW_RE.sub("", txt)
    return re.sub(r"\s{2,}", " ", txt).strip()


def extract_public_email(*texts: str) -> str | None:
    for blob in texts:
        if not blob:
            continue
        clean_blob = re.sub(r"\s*\[at\]\s*|\s*\(at\)\s*", "@", html.unescape(str(blob)), flags=re.IGNORECASE)
        clean_blob = re.sub(r"\s*\[dot\]\s*|\s*\(dot\)\s*", ".", clean_blob, flags=re.IGNORECASE)
        for m in EMAIL_RE.finditer(clean_blob):
            cand = m.group(1).strip().rstrip(".,;:!?").lower()
            local, domain = cand.split("@", 1)
            if not local or domain in BLOCKED_EMAIL_DOMAINS or domain.endswith((".noreply.github.com", ".local", ".internal")):
                continue
            if cand.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")):
                continue
            return cand
    return None


def _is_fresh_file(path: str, max_age_hours: float) -> bool:
    if max_age_hours <= 0 or not os.path.exists(path):
        return False
    age_sec = datetime.now(timezone.utc).timestamp() - os.path.getmtime(path)
    return 0 <= age_sec < (max_age_hours * 3600)


# ---------------------------------------------------------------------------
# PRODUCT A: BASE & SOLANA FRESH LAUNCH ALPHA FEED
# ---------------------------------------------------------------------------
def _extract_gecko_pool(chain: str, pool: dict) -> dict | None:
    attr = pool.get("attributes") or {}
    rel = pool.get("relationships") or {}
    base_rel_id = ((rel.get("base_token") or {}).get("data") or {}).get("id") or ""
    dex_id = ((rel.get("dex") or {}).get("data") or {}).get("id") or "dex"

    token_addr = base_rel_id.split("_", 1)[1] if "_" in base_rel_id else ""
    if chain == "base":
        token_addr = token_addr.lower()
        if not token_addr or token_addr in QUOTE_BASE_TOKENS:
            return None
    else:
        if not token_addr or token_addr in QUOTE_SOL_MINTS:
            return None

    pool_id = pool.get("id") or ""
    pool_addr = pool_id.split("_", 1)[1] if "_" in pool_id else (attr.get("address") or "")
    raw_name = str(attr.get("name") or "")
    has_spoof_zw = bool(ZW_RE.search(raw_name))
    name_clean = _clean_text(raw_name)
    symbol = name_clean.split("/", 1)[0].strip()[:24] if "/" in name_clean else name_clean[:24]

    tx24 = ((attr.get("transactions") or {}).get("h24") or {})
    buys = _safe_int(tx24.get("buys"))
    sells = _safe_int(tx24.get("sells"))
    reserve_usd = round(_safe_float(attr.get("reserve_in_usd")), 2)
    vol24 = round(_safe_float((attr.get("volume_usd") or {}).get("h24")), 2)

    return {
        "chain": chain,
        "token_address": token_addr,
        "pool_address": pool_addr,
        "symbol": symbol or "UNKNOWN",
        "pair_name": name_clean,
        "dex": dex_id,
        "price_usd": _safe_float(attr.get("base_token_price_usd")),
        "reserve_usd": reserve_usd,
        "liquidity_over_10k": reserve_usd >= 10000.0,
        "fdv_usd": round(_safe_float(attr.get("fdv_usd")), 2),
        "market_cap_usd": round(_safe_float(attr.get("market_cap_usd")), 2),
        "volume_24h_usd": vol24,
        "txns_24h_buys": buys,
        "txns_24h_sells": sells,
        "pool_created_at": attr.get("pool_created_at") or "",
        "social_links": [],
        "website": None,
        "deployer_dump_risk": "unknown",
        "anomaly_flags": ["zero_width_symbol_spoof"] if has_spoof_zw else [],
        "security": {},
        "source": "geckoterminal",
    }


def _enrich_dexscreener(records_by_key: dict[tuple[str, str], dict]) -> None:
    addresses = list({addr for (_, addr) in records_by_key.keys() if addr})
    chunks = [addresses[i : i + 28] for i in range(0, min(len(addresses), 140), 28)]

    def _fetch_chunk(chunk):
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{','.join(chunk)}"
            return fetch_json(url, timeout=10).get("pairs") or []
        except Exception:
            return []

    best_pair: dict[tuple[str, str], dict] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for pairs in pool.map(_fetch_chunk, chunks):
            for p in pairs:
                chain = (p.get("chainId") or "").lower()
                if chain not in ("base", "solana"):
                    continue
                addr = (p.get("baseToken") or {}).get("address") or ""
                key_addr = addr.lower() if chain == "base" else addr
                k = (chain, key_addr)
                if k not in records_by_key:
                    continue
                liq = _safe_float((p.get("liquidity") or {}).get("usd"))
                prev_liq = _safe_float((best_pair.get(k, {}).get("liquidity") or {}).get("usd"))
                if k not in best_pair or liq > prev_liq:
                    best_pair[k] = p

    for k, rec in records_by_key.items():
        p = best_pair.get(k)
        if not p:
            continue
        bt = p.get("baseToken") or {}
        if bt.get("symbol"):
            if ZW_RE.search(str(bt["symbol"])) and "zero_width_symbol_spoof" not in rec["anomaly_flags"]:
                rec["anomaly_flags"].append("zero_width_symbol_spoof")
            rec["symbol"] = _clean_text(bt["symbol"])[:24] or rec["symbol"]
        if bt.get("name"):
            rec["token_name"] = _clean_text(bt["name"])[:60]
        liq_usd = _safe_float((p.get("liquidity") or {}).get("usd"))
        if liq_usd > rec["reserve_usd"]:
            rec["reserve_usd"] = round(liq_usd, 2)
            rec["liquidity_over_10k"] = rec["reserve_usd"] >= 10000.0
        vol24 = _safe_float((p.get("volume") or {}).get("h24"))
        if vol24 > rec["volume_24h_usd"]:
            rec["volume_24h_usd"] = round(vol24, 2)
        if p.get("fdv") and not rec["fdv_usd"]:
            rec["fdv_usd"] = round(_safe_float(p.get("fdv")), 2)
        if p.get("dexId"):
            rec["dex"] = str(p["dexId"])
        if p.get("url"):
            rec["dexscreener_url"] = p["url"]
        info = p.get("info") or {}
        websites = [w.get("url") for w in (info.get("websites") or []) if isinstance(w, dict) and w.get("url")]
        socials = [
            {"type": s.get("type") or "social", "url": s.get("url")}
            for s in (info.get("socials") or [])
            if isinstance(s, dict) and s.get("url")
        ]
        if websites:
            rec["website"] = websites[0]
        rec["social_links"] = (websites[:2] + [s["url"] for s in socials])[:6]


def _classify_base_deployer_risk(sec: dict) -> str:
    if not sec:
        return "unknown"
    honeypot = str(sec.get("is_honeypot") or "") == "1"
    cannot_sell = str(sec.get("cannot_sell_all") or "") == "1"
    buy_tax = _safe_float(sec.get("buy_tax"))
    sell_tax = _safe_float(sec.get("sell_tax"))
    creator_pct = _safe_float(sec.get("creator_percent"))
    if honeypot or cannot_sell or sell_tax > 0.25 or buy_tax > 0.25:
        return "critical"
    if creator_pct > 0.15 or sell_tax > 0.08 or buy_tax > 0.08:
        return "high"
    if creator_pct > 0.05 or str(sec.get("is_open_source") or "") == "0":
        return "medium"
    return "low"


def _enrich_goplus_base(base_records: list[dict]) -> None:
    addrs = [r["token_address"] for r in base_records if r.get("token_address")]
    chunks = [addrs[i : i + 20] for i in range(0, min(len(addrs), 80), 20)]

    def _fetch_sec(chunk):
        try:
            url = f"https://api.gopluslabs.io/api/v1/token_security/8453?contract_addresses={','.join(chunk)}"
            return fetch_json(url, timeout=10).get("result") or {}
        except Exception:
            return {}

    sec_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for res in pool.map(_fetch_sec, chunks):
            if isinstance(res, dict):
                for addr, info in res.items():
                    sec_map[addr.lower()] = info

    for r in base_records:
        info = sec_map.get(r["token_address"].lower())
        if not info:
            continue
        r["deployer_dump_risk"] = _classify_base_deployer_risk(info)
        r["security"] = {
            "provider": "goplus_base_8453",
            "is_honeypot": str(info.get("is_honeypot") or "") == "1",
            "is_open_source": str(info.get("is_open_source") or "") == "1",
            "cannot_sell_all": str(info.get("cannot_sell_all") or "") == "1",
            "buy_tax_pct": round(_safe_float(info.get("buy_tax")) * 100, 2),
            "sell_tax_pct": round(_safe_float(info.get("sell_tax")) * 100, 2),
            "creator_address": info.get("creator_address") or None,
            "creator_percent": round(_safe_float(info.get("creator_percent")) * 100, 3),
            "owner_address": info.get("owner_address") or None,
            "holder_count": _safe_int(info.get("holder_count")),
        }


def _enrich_rugcheck_solana(sol_records: list[dict]) -> None:
    targets = sol_records[:25]

    def _fetch_rc(rec):
        try:
            url = f"https://api.rugcheck.xyz/v1/tokens/{urllib.parse.quote(rec['token_address'])}/report/summary"
            return rec["token_address"], fetch_json(url, timeout=8)
        except Exception:
            return rec["token_address"], None

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = dict(pool.map(_fetch_rc, targets))

    for r in targets:
        rc = results.get(r["token_address"])
        if not isinstance(rc, dict):
            continue
        score_norm = _safe_float(rc.get("score_normalised"), default=-1.0)
        lp_locked = _safe_float(rc.get("lpLockedPct"))
        risks = [rk.get("name") for rk in (rc.get("risks") or []) if isinstance(rk, dict) and rk.get("name")]
        if score_norm >= 70 or len(risks) >= 3:
            r["deployer_dump_risk"] = "high"
        elif score_norm >= 35 or len(risks) >= 1:
            r["deployer_dump_risk"] = "medium"
        elif score_norm >= 0:
            r["deployer_dump_risk"] = "low"
        r["security"] = {
            "provider": "rugcheck_solana",
            "score": _safe_float(rc.get("score")),
            "score_normalised": score_norm if score_norm >= 0 else None,
            "lp_locked_pct": round(lp_locked, 2),
            "token_program": rc.get("tokenProgram") or None,
            "risk_flags": risks[:6],
        }


def compile_base_solana_alpha() -> dict:
    records: dict[tuple[str, str], dict] = {}
    pool_specs = [
        ("base", "https://api.geckoterminal.com/api/v2/networks/base/new_pools?page=1"),
        ("base", "https://api.geckoterminal.com/api/v2/networks/base/new_pools?page=2"),
        ("base", "https://api.geckoterminal.com/api/v2/networks/base/new_pools?page=3"),
        ("solana", "https://api.geckoterminal.com/api/v2/networks/solana/new_pools?page=1"),
        ("solana", "https://api.geckoterminal.com/api/v2/networks/solana/new_pools?page=2"),
    ]

    def _fetch_pools(spec):
        chain, url = spec
        try:
            return chain, fetch_json(url, timeout=12).get("data") or []
        except Exception:
            return chain, []

    with ThreadPoolExecutor(max_workers=5) as pool:
        for chain, items in pool.map(_fetch_pools, pool_specs):
            for p in items:
                rec = _extract_gecko_pool(chain, p)
                if not rec:
                    continue
                key = (chain, rec["token_address"])
                if key not in records or rec["reserve_usd"] > records[key]["reserve_usd"]:
                    records[key] = rec

    try:
        profiles = fetch_json("https://api.dexscreener.com/token-profiles/latest/v1", timeout=10)
        if isinstance(profiles, list):
            for prof in profiles:
                chain = (prof.get("chainId") or "").lower()
                if chain not in ("base", "solana"):
                    continue
                addr = (prof.get("tokenAddress") or "").strip()
                if not addr:
                    continue
                norm_addr = addr.lower() if chain == "base" else addr
                if (chain == "base" and norm_addr in QUOTE_BASE_TOKENS) or (chain == "solana" and norm_addr in QUOTE_SOL_MINTS):
                    continue
                key = (chain, norm_addr)
                if key not in records:
                    links = [lk.get("url") for lk in (prof.get("links") or []) if isinstance(lk, dict) and lk.get("url")]
                    records[key] = {
                        "chain": chain,
                        "token_address": norm_addr,
                        "pool_address": "",
                        "symbol": "PROFILE",
                        "pair_name": _clean_text(prof.get("description") or "")[:40] or norm_addr[:10],
                        "dex": "dexscreener",
                        "price_usd": 0.0,
                        "reserve_usd": 0.0,
                        "liquidity_over_10k": False,
                        "fdv_usd": 0.0,
                        "market_cap_usd": 0.0,
                        "volume_24h_usd": 0.0,
                        "txns_24h_buys": 0,
                        "txns_24h_sells": 0,
                        "pool_created_at": "",
                        "social_links": links[:6],
                        "website": links[0] if links else None,
                        "deployer_dump_risk": "unknown",
                        "anomaly_flags": [],
                        "security": {},
                        "source": "dexscreener_profile",
                    }
    except Exception:
        pass

    _enrich_dexscreener(records)

    base_list = sorted([r for r in records.values() if r["chain"] == "base"], key=lambda x: x["reserve_usd"], reverse=True)
    sol_list = sorted([r for r in records.values() if r["chain"] == "solana"], key=lambda x: x["reserve_usd"], reverse=True)

    _enrich_goplus_base(base_list)
    _enrich_rugcheck_solana(sol_list)

    combined = []
    for r in (base_list[:65] + sol_list[:45]):
        if r["reserve_usd"] < 500.0:
            continue
        # Flag extreme TVL-vs-volume discrepancy (common thin-pool spoof pattern)
        if r["reserve_usd"] > 5_000_000 and r["volume_24h_usd"] < (r["reserve_usd"] * 0.005):
            if "extreme_tvl_low_volume_anomaly" not in r["anomaly_flags"]:
                r["anomaly_flags"].append("extreme_tvl_low_volume_anomaly")
        combined.append(r)

    combined.sort(
        key=lambda r: (
            len(r["anomaly_flags"]) == 0,
            r["liquidity_over_10k"],
            r["deployer_dump_risk"] == "low",
            r["reserve_usd"],
        ),
        reverse=True,
    )
    tokens = combined[:90]

    return {
        "product": "base-alpha-feed",
        "title": "Base & Solana Fresh Token Launch Alpha Feed",
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "sources": [
            "GeckoTerminal New Pools API (Base & Solana)",
            "DexScreener Token Profiles & Pair Liquidity API",
            "GoPlus EVM Security API (Chain 8453)",
            "RugCheck Solana Risk Summary API",
        ],
        "total_tokens": len(tokens),
        "base_count": sum(1 for t in tokens if t["chain"] == "base"),
        "solana_count": sum(1 for t in tokens if t["chain"] == "solana"),
        "over_10k_liquidity_count": sum(1 for t in tokens if t["liquidity_over_10k"]),
        "low_risk_count": sum(1 for t in tokens if t["deployer_dump_risk"] == "low"),
        "tokens": tokens,
    }


# ---------------------------------------------------------------------------
# PRODUCT B: FRESH AI & SAAS STARTUP INTENT LEADS (UP TO 500 VERIFIED ROWS)
# ---------------------------------------------------------------------------
def _infer_tech_stack(text: str) -> list[str]:
    low = (text or "").lower()
    tags = []
    checks = [
        ("AI/LLM", ("ai", "llm", "gpt", "claude", "agent", "rag", "mcp", "model")),
        ("SaaS", ("saas", "b2b", "dashboard", "workflow", "automation")),
        ("TypeScript/React", ("typescript", "react", "next.js", "nextjs", "node")),
        ("Python/FastAPI", ("python", "fastapi", "pytorch", "django")),
        ("Rust", ("rust", "cargo")),
        ("Go", ("golang", " go ")),
        ("Cloud/DevOps", ("kubernetes", "docker", "cloudflare", "aws", "postgres")),
    ]
    for label, kws in checks:
        if any(kw in low for kw in kws):
            tags.append(label)
    return tags or ["Software/Tech"]


def compile_b2b_startup_leads(target_count: int = 500, gh_token: str = "") -> dict:
    gh_tok = gh_token or resolve_gh_token()
    since_14d = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    leads_by_key: dict[str, dict] = {}

    def _add_lead(row: dict):
        domain = (row.get("domain") or "").lower().strip()
        company = (row.get("company_name") or "").lstrip("@").strip()
        row["company_name"] = company
        key = domain if (domain and domain not in ("unknown", "github.com", "news.ycombinator.com", "remotive.com")) else f"{row.get('source_type')}:{company.lower()}"
        if not key or not company:
            return
        existing = leads_by_key.get(key)
        if not existing:
            leads_by_key[key] = row
        elif not existing.get("email") and row.get("email"):
            existing["email"] = row["email"]

    # 1. Hacker News Show HN launches (pages 0..2)
    for page in (0, 1, 2):
        try:
            url = f"https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&hitsPerPage=100&page={page}"
            hits = fetch_json(url, timeout=10).get("hits") or []
            for h in hits:
                raw_title = _clean_text(h.get("title") or "")
                if not raw_title:
                    continue
                clean_title = re.sub(r"^(?:Show HN|Launch HN):\s*", "", raw_title, flags=re.IGNORECASE).strip()
                company = re.split(r"\s+[–—\-|:]\s+|:\s+", clean_title, maxsplit=1)[0].strip()[:48]
                website = (h.get("url") or "").strip()
                domain = "unknown"
                if website.startswith("http"):
                    try:
                        domain = urllib.parse.urlparse(website).netloc.lower().removeprefix("www.")
                    except Exception:
                        pass
                story_text = _clean_text(h.get("story_text") or "")
                email = extract_public_email(story_text)
                points = _safe_int(h.get("points"), 1)
                comments = _safe_int(h.get("num_comments"), 0)
                hiring = ("hiring" in story_text.lower()) or points >= 25
                score = min(100, max(35, points * 2 + comments * 3 + (20 if hiring else 0) + (15 if email else 0)))
                _add_lead({
                    "company_name": company,
                    "launch_headline": clean_title[:140],
                    "domain": domain,
                    "website_url": website or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    "source_type": "show_hn",
                    "source_url": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    "founder_or_contact": h.get("author") or None,
                    "email": email,
                    "tech_stack": _infer_tech_stack(f"{clean_title} {story_text[:500]}"),
                    "hiring_intent": hiring,
                    "intent_score": score,
                    "published_at": h.get("created_at") or "",
                })
        except Exception:
            pass

    # 2. Hacker News YC Jobs + Latest "Who is hiring" thread (pages 0..1)
    try:
        jobs = fetch_json("https://hn.algolia.com/api/v1/search_by_date?tags=job&hitsPerPage=100", timeout=10).get("hits") or []
        for j in jobs:
            title = _clean_text(j.get("title") or "")
            if not title:
                continue
            company = re.split(r"\s+(?:is hiring|hires|\(|–|-)\s*", title, maxsplit=1, flags=re.IGNORECASE)[0].strip()[:48]
            website = (j.get("url") or "").strip()
            domain = "unknown"
            if website.startswith("http"):
                try:
                    domain = urllib.parse.urlparse(website).netloc.lower().removeprefix("www.")
                except Exception:
                    pass
            body = _clean_text(j.get("story_text") or "")
            email = extract_public_email(body)
            _add_lead({
                "company_name": company or "YC Hiring Startup",
                "launch_headline": title[:140],
                "domain": domain,
                "website_url": website or f"https://news.ycombinator.com/item?id={j.get('objectID')}",
                "source_type": "hn_yc_job",
                "source_url": f"https://news.ycombinator.com/item?id={j.get('objectID')}",
                "founder_or_contact": j.get("author") or None,
                "email": email,
                "tech_stack": _infer_tech_stack(f"{title} {body[:500]}"),
                "hiring_intent": True,
                "intent_score": 88 if email else 78,
                "published_at": j.get("created_at") or "",
            })
    except Exception:
        pass

    try:
        wh = fetch_json("https://hn.algolia.com/api/v1/search_by_date?query=%22Who%20is%20hiring%22&tags=story&hitsPerPage=3", timeout=8)
        top_thread = next((h for h in (wh.get("hits") or []) if "who is hiring" in (h.get("title") or "").lower()), None)
        if top_thread and top_thread.get("objectID"):
            thread_id = top_thread["objectID"]
            for page in (0, 1):
                comments = fetch_json(
                    f"https://hn.algolia.com/api/v1/search_by_date?tags=comment,story_{thread_id}&hitsPerPage=100&page={page}",
                    timeout=10,
                ).get("hits") or []
                for c in comments:
                    raw_txt = _clean_text(c.get("comment_text") or "")
                    if len(raw_txt) < 40:
                        continue
                    first_line = raw_txt.split("|", 1)[0].strip()
                    company = first_line[:45].split("http")[0].strip()
                    url_m = re.search(r"https?://[^\s<>\"')]+", raw_txt)
                    website = url_m.group(0).rstrip(".,;)") if url_m else ""
                    domain = "unknown"
                    if website:
                        try:
                            domain = urllib.parse.urlparse(website).netloc.lower().removeprefix("www.")
                        except Exception:
                            pass
                    email = extract_public_email(raw_txt)
                    _add_lead({
                        "company_name": company or (c.get("author") or "Hiring Startup"),
                        "launch_headline": raw_txt[:140],
                        "domain": domain,
                        "website_url": website or f"https://news.ycombinator.com/item?id={c.get('objectID')}",
                        "source_type": "hn_who_is_hiring",
                        "source_url": f"https://news.ycombinator.com/item?id={c.get('objectID')}",
                        "founder_or_contact": c.get("author") or None,
                        "email": email,
                        "tech_stack": _infer_tech_stack(raw_txt[:500]),
                        "hiring_intent": True,
                        "intent_score": 92 if email else 80,
                        "published_at": c.get("created_at") or "",
                    })
    except Exception:
        pass

    # 3. Remotive Remote Software/AI Jobs
    try:
        rem = fetch_json("https://remotive.com/api/remote-jobs?category=software-dev&limit=100", timeout=10)
        for job in (rem.get("jobs") or [])[:100]:
            co = _clean_text(job.get("company_name") or "")[:48]
            if not co:
                continue
            job_url = job.get("url") or ""
            _add_lead({
                "company_name": co,
                "launch_headline": f"Hiring: {_clean_text(job.get('title') or 'Software Engineer')}"[:140],
                "domain": "remotive.com",
                "website_url": job_url,
                "source_type": "remotive_hiring",
                "source_url": job_url,
                "founder_or_contact": job.get("candidate_required_location") or "Remote",
                "email": None,
                "tech_stack": (job.get("tags") or [])[:5] or _infer_tech_stack(job.get("title") or ""),
                "hiring_intent": True,
                "intent_score": 74,
                "published_at": job.get("publication_date") or "",
            })
    except Exception:
        pass

    # 4. Newly launched GitHub AI / SaaS / MCP / Agent repositories (last 14 days)
    gh_hdrs = {"Accept": "application/vnd.github.v3+json"}
    if gh_tok:
        gh_hdrs["Authorization"] = f"Bearer {gh_tok}"

    gh_queries = [
        f"created:>{since_14d} topic:ai stars:>3",
        f"created:>{since_14d} topic:saas stars:>2",
        f"created:>{since_14d} topic:mcp stars:>2",
        f"created:>{since_14d} topic:ai-agents stars:>2",
        f"created:>{since_14d} topic:llm stars:>3",
        f"created:>{since_14d} topic:devtools stars:>2",
    ]
    gh_repos = []
    seen_repo_names = set()
    for q in gh_queries:
        if len(leads_by_key) + len(gh_repos) >= target_count + 120:
            break
        try:
            url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(q)}&sort=stars&order=desc&per_page=80"
            for r in (fetch_json(url, timeout=10, headers=gh_hdrs).get("items") or []):
                fn = r.get("full_name")
                if fn and fn not in seen_repo_names:
                    seen_repo_names.add(fn)
                    gh_repos.append(r)
        except Exception:
            continue

    seen_owners: dict[str, dict] = {}
    top_owners = []
    for repo in gh_repos:
        login = ((repo.get("owner") or {}).get("login") or "").strip()
        if login and login not in seen_owners and len(top_owners) < 90:
            seen_owners[login] = {}
            top_owners.append(login)

    def _fetch_owner(login: str):
        try:
            return login, fetch_json(f"https://api.github.com/users/{urllib.parse.quote(login)}", timeout=5, headers=gh_hdrs)
        except Exception:
            return login, {}

    if top_owners:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for login, meta in pool.map(_fetch_owner, top_owners):
                seen_owners[login] = meta if isinstance(meta, dict) else {}

    # Enrich public non-noreply author email from recent repo commits when profile email is empty
    repos_needing_commit_email = []
    for repo in gh_repos[:80]:
        login = ((repo.get("owner") or {}).get("login") or "").strip()
        owner_meta = seen_owners.get(login) or {}
        if not extract_public_email(owner_meta.get("email") or "", owner_meta.get("bio") or ""):
            repos_needing_commit_email.append(repo.get("full_name"))

    commit_emails: dict[str, str] = {}
    def _fetch_commit_email(full_name: str):
        try:
            commits = fetch_json(
                f"https://api.github.com/repos/{full_name}/commits?per_page=2",
                timeout=5,
                headers=gh_hdrs,
            )
            if isinstance(commits, list):
                for c in commits:
                    cand = ((c.get("commit") or {}).get("author") or {}).get("email")
                    pub = extract_public_email(cand or "")
                    if pub:
                        return full_name, pub
        except Exception:
            pass
        return full_name, None

    if repos_needing_commit_email:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for fn, em in pool.map(_fetch_commit_email, repos_needing_commit_email):
                if em:
                    commit_emails[fn] = em

    for repo in gh_repos:
        full_name = repo.get("full_name") or ""
        if not full_name:
            continue
        login = ((repo.get("owner") or {}).get("login") or "").strip()
        owner_meta = seen_owners.get(login) or {}
        homepage = (repo.get("homepage") or owner_meta.get("blog") or "").strip()
        if homepage and not homepage.startswith(("http://", "https://")):
            homepage = f"https://{homepage}"
        domain = "github.com"
        if homepage.startswith(("http://", "https://")):
            try:
                domain = urllib.parse.urlparse(homepage).netloc.lower().removeprefix("www.") or "github.com"
            except Exception:
                domain = "github.com"
        desc = _clean_text(repo.get("description") or "")
        email = extract_public_email(
            owner_meta.get("email") or "",
            owner_meta.get("bio") or "",
            desc,
            commit_emails.get(full_name) or "",
        )
        stars = _safe_int(repo.get("stargazers_count"))
        topics = [str(t) for t in (repo.get("topics") or [])[:4]]
        lang = (repo.get("language") or "").strip()
        stack = ([lang] if lang else []) + topics
        if not stack:
            stack = _infer_tech_stack(desc)
        raw_co = _clean_text(owner_meta.get("company") or repo.get("name") or full_name).lstrip("@").strip()
        _add_lead({
            "company_name": raw_co[:48],
            "launch_headline": desc[:140] or f"New GitHub launch: {full_name}",
            "domain": domain,
            "website_url": homepage or repo.get("html_url") or "",
            "source_type": "github_new_launch",
            "source_url": repo.get("html_url") or "",
            "founder_or_contact": _clean_text(owner_meta.get("name") or login or "") or None,
            "email": email,
            "tech_stack": stack[:6],
            "hiring_intent": bool(owner_meta.get("hireable")),
            "intent_score": min(100, 45 + min(30, stars // 3) + (15 if email else 0)),
            "published_at": repo.get("created_at") or "",
        })

    all_leads = list(leads_by_key.values())
    all_leads.sort(
        key=lambda r: (bool(r.get("email")), bool(r.get("hiring_intent")), _safe_int(r.get("intent_score"))),
        reverse=True,
    )
    final_leads = all_leads[:target_count]

    return {
        "product": "b2b-startup-leads-500",
        "title": "Fresh AI & SaaS Startup Intent Leads Drop",
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "window_days": 14,
        "sources": [
            "Hacker News Show HN Launches (Algolia API)",
            "Hacker News YC Jobs & Who Is Hiring Thread",
            "Remotive Active Software & AI Hiring Feed",
            "GitHub Newly Launched AI/SaaS/MCP Repositories",
        ],
        "total_leads": len(final_leads),
        "verified_email_count": sum(1 for r in final_leads if r.get("email")),
        "hiring_count": sum(1 for r in final_leads if r.get("hiring_intent")),
        "leads": final_leads,
    }


def main():
    parser = argparse.ArgumentParser(description="Compile live store datasets for AgentFuel402 /store")
    parser.add_argument("--if-stale-hours", type=float, default=0.0, help="Skip products modified within N hours")
    parser.add_argument("--max-leads", type=int, default=500, help="Maximum B2B leads to compile (default: 500)")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    gh_token = resolve_gh_token()

    alpha_updated = False
    leads_updated = False

    if _is_fresh_file(BASE_ALPHA_PATH, args.if_stale_hours):
        print(f"[=] {BASE_ALPHA_PATH} is fresh (<{args.if_stale_hours}h), skipping.")
    else:
        alpha = compile_base_solana_alpha()
        with open(BASE_ALPHA_PATH, "w", encoding="utf-8") as f:
            json.dump(alpha, f, indent=2)
        alpha_updated = True
        print(
            f"[+] Compiled {BASE_ALPHA_PATH}: {alpha['total_tokens']} tokens "
            f"(Base={alpha['base_count']}, Solana={alpha['solana_count']}, >$10k={alpha['over_10k_liquidity_count']})"
        )

    if _is_fresh_file(B2B_LEADS_PATH, args.if_stale_hours):
        print(f"[=] {B2B_LEADS_PATH} is fresh (<{args.if_stale_hours}h), skipping.")
    else:
        leads = compile_b2b_startup_leads(target_count=args.max_leads, gh_token=gh_token)
        with open(B2B_LEADS_PATH, "w", encoding="utf-8") as f:
            json.dump(leads, f, indent=2)
        leads_updated = True
        print(
            f"[+] Compiled {B2B_LEADS_PATH}: {leads['total_leads']} leads "
            f"(emails={leads['verified_email_count']}, hiring={leads['hiring_count']})"
        )

    if alpha_updated or leads_updated or not os.path.exists(STORE_SNAPSHOTS_JS_PATH):
        with open(BASE_ALPHA_PATH, "r", encoding="utf-8") as f:
            alpha_obj = json.load(f)
        with open(B2B_LEADS_PATH, "r", encoding="utf-8") as f:
            leads_obj = json.load(f)
        with open(STORE_SNAPSHOTS_JS_PATH, "w", encoding="utf-8") as f:
            f.write("// Auto-generated by scripts/compile_store_products.py from latest_base_alpha.json & latest_b2b_leads.json\n")
            f.write(f"export const BASE_ALPHA_SNAPSHOT = {json.dumps(alpha_obj, separators=(',', ':'))};\n")
            f.write(f"export const B2B_LEADS_SNAPSHOT = {json.dumps(leads_obj, separators=(',', ':'))};\n")
        print(f"[+] Synced {STORE_SNAPSHOTS_JS_PATH}")


if __name__ == "__main__":
    main()
