#!/usr/bin/env python3
"""
AgentFuel402 Agency Arbitrage & Productized Data Pack Engine
Shifts outreach & fulfillment from micro-APIs to high-ticket productized assets ($39-$249):
  1. B2B Agency Lead Pack Generator (up to 200+ live AI/SaaS/E-Com/Agency intent leads + 5-row sample)
  2. E-Commerce Competitor Price & Stock Matrix Generator (Shopify / WooCommerce / Schema.org)
  3. High-Intent Business Buyer Prospecting + Free Security/Price Audit Lead Magnets
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta, timezone
import html
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

try:
    import compile_store_products as csp
except ImportError:
    from scripts import compile_store_products as csp

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
DATA_DIR = os.path.join(REPO_ROOT, "data")
DELIVERABLES_DIR = os.path.join(DATA_DIR, "deliverables")

STORE_BASE_URL = "https://agentfuel402.ak10082247.workers.dev"
STRIPE_AGENCY_PACK_URL = f"{STORE_BASE_URL}/v1/checkout/bundle?sku=agency-pack"
STRIPE_PRO_KEY_URL = f"{STORE_BASE_URL}/v1/checkout/api-key?plan=pro"
STRIPE_STARTER_KEY_URL = f"{STORE_BASE_URL}/v1/checkout/api-key?plan=starter"
STORE_URL = f"{STORE_BASE_URL}/store"

APIFY_B2B_ACTOR_ID = "2AbJGn42avqlwZo5V"
APIFY_ECOM_ACTOR_ID = "JoVOb6vKPFaNhDDcj"

UA = "AgentFuel402-AgencyDealmaker/1.0 (+https://agentfuel402.ak10082247.workers.dev/store)"
MAILTO_RE = re.compile(r'mailto:([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})', re.IGNORECASE)
GENERIC_SITE_BLOCKLIST = {
    "github.com", "gitlab.com", "youtube.com", "youtu.be", "twitter.com", "x.com",
    "linkedin.com", "instagram.com", "facebook.com", "tiktok.com", "reddit.com",
    "news.ycombinator.com", "producthunt.com", "medium.com", "substack.com",
    "remotive.com", "wikipedia.org", "npmjs.com", "pypi.org", "cloudflare.com",
}

try:
    SSL_CTX = ssl._create_unverified_context()
except Exception:
    SSL_CTX = None


def _http_get_text(url: str, timeout: int = 8, headers: dict | None = None) -> tuple[int, str, str]:
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    kwargs = {"timeout": timeout}
    if SSL_CTX is not None:
        kwargs["context"] = SSL_CTX
    with urllib.request.urlopen(req, **kwargs) as resp:
        return resp.status, resp.geturl(), resp.read().decode("utf-8", "replace")


def _http_post_json(url: str, payload: dict, timeout: int = 20, headers: dict | None = None):
    hdrs = {"User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=hdrs)
    kwargs = {"timeout": timeout}
    if SSL_CTX is not None:
        kwargs["context"] = SSL_CTX
    with urllib.request.urlopen(req, **kwargs) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _classify_niche(text: str) -> str:
    low = (text or "").lower()
    if any(k in low for k in ("shopify", "woocommerce", "ecommerce", "e-commerce", "dtc", "retail", "storefront", "checkout", "dropship")):
        return "ecommerce"
    if any(k in low for k in ("agency", "marketing", "lead gen", "lead-gen", "b2b outreach", "seo", "retainer", "client workflow", "consulting")):
        return "agency"
    if any(k in low for k in ("ai", "llm", "agent", "rag", "mcp", "gpt", "claude", "copilot")):
        return "ai"
    return "saas"


def _matches_niche_filter(niche_filter: str, lead: dict) -> bool:
    nf = (niche_filter or "all").lower().strip()
    if nf in ("", "all"):
        return True
    seg = (lead.get("niche_segment") or "").lower()
    blob = f"{lead.get('company_name', '')} {lead.get('launch_headline', '')} {' '.join(lead.get('tech_stack') or [])}".lower()
    return seg == nf or nf in blob


def fetch_producthunt_launches(limit: int = 40) -> list[dict]:
    """Parse live Product Hunt launches from official Atom feed."""
    items = []
    try:
        _, _, xml_text = _http_get_text("https://www.producthunt.com/feed", timeout=10)
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns)[:limit]:
            title = csp._clean_text(entry.findtext("atom:title", "", ns))
            if not title:
                continue
            link_el = entry.find("atom:link", ns)
            ph_url = (link_el.attrib.get("href") or "").strip() if link_el is not None else ""
            content_raw = entry.findtext("atom:content", "", ns) or ""
            tagline = csp._clean_text(content_raw).split("Discussion | Link")[0].strip()
            author_el = entry.find("atom:author/atom:name", ns)
            maker = csp._clean_text(author_el.text if author_el is not None else "") or None
            published = (entry.findtext("atom:published", "", ns) or entry.findtext("atom:updated", "", ns) or "").strip()

            redirect_m = re.search(r'href="(https://www\.producthunt\.com/r/p/[^"]+)"', content_raw)
            redirect_url = html.unescape(redirect_m.group(1)) if redirect_m else ph_url
            items.append({
                "company_name": title[:48],
                "launch_headline": (tagline or title)[:160],
                "ph_url": ph_url,
                "redirect_url": redirect_url,
                "maker": maker,
                "published_at": published,
            })
    except Exception:
        pass
    return items


def _resolve_redirect_url(url: str, timeout: int = 4) -> str:
    if not url or "producthunt.com/r/p/" not in url:
        return url
    try:
        _, final_url, _ = _http_get_text(url, timeout=timeout)
        if final_url and "producthunt.com" not in final_url:
            return final_url.split("?utm_")[0]
    except Exception:
        pass
    return url


def extract_business_contact_from_site(website_url: str, email_validator=None) -> dict:
    """Inspect a public business homepage & /contact page for real published contact email & title."""
    validator = email_validator or csp.extract_public_email
    res = {"website_url": website_url, "title": "", "email": None, "text_excerpt": ""}
    if not website_url or not website_url.startswith(("http://", "https://")):
        return res
    try:
        host = urllib.parse.urlparse(website_url).netloc.lower().removeprefix("www.")
        if not host or any(host == b or host.endswith("." + b) for b in GENERIC_SITE_BLOCKLIST):
            return res
    except Exception:
        return res

    base_origin = f"{urllib.parse.urlparse(website_url).scheme}://{urllib.parse.urlparse(website_url).netloc}"
    pages_to_check = [website_url]
    if urllib.parse.urlparse(website_url).path in ("", "/"):
        pages_to_check.append(f"{base_origin}/contact")

    for target in pages_to_check:
        try:
            _, _, body = _http_get_text(target, timeout=4)
            if not res["title"]:
                tm = re.search(r"<title[^>]*>([^<]+)</title>", body, re.IGNORECASE)
                if tm:
                    res["title"] = csp._clean_text(tm.group(1))[:100]
            if not res["text_excerpt"]:
                stripped = csp._clean_text(re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", body, flags=re.IGNORECASE))
                res["text_excerpt"] = stripped[:600]

            mailtos = [m.group(1).lower().strip() for m in MAILTO_RE.finditer(body)]
            for cand in mailtos:
                if callable(email_validator) and email_validator is not csp.extract_public_email:
                    if email_validator(cand):
                        res["email"] = cand
                        return res
                else:
                    pub = csp.extract_public_email(cand)
                    if pub:
                        res["email"] = pub
                        return res

            fallback_em = csp.extract_public_email(body)
            if fallback_em:
                if email_validator is None or email_validator is csp.extract_public_email or email_validator(fallback_em):
                    res["email"] = fallback_em
                    return res
        except Exception:
            continue
    return res


def _fetch_apify_b2b_leads(limit: int, niche: str, apify_token: str) -> list[dict]:
    if not apify_token:
        return []
    url = f"https://api.apify.com/v2/acts/{APIFY_B2B_ACTOR_ID}/run-sync-get-dataset-items?token={urllib.parse.quote(apify_token)}"
    rows = _http_post_json(url, {"limit": limit, "category": niche if niche != "agency" else "saas"}, timeout=60)
    out = []
    for item in (rows if isinstance(rows, list) else []):
        if not isinstance(item, dict) or not item.get("company_name"):
            continue
        headline = csp._clean_text(item.get("launch_headline") or "")
        out.append({
            "company_name": csp._clean_text(item.get("company_name"))[:60],
            "niche_segment": _classify_niche(f"{headline} {' '.join(item.get('detected_tech_stack') or [])}"),
            "domain": (item.get("domain") or "unknown").lower(),
            "website_url": item.get("source_url") or "",
            "launch_headline": headline[:160],
            "decision_maker": item.get("author") or None,
            "contact_email": None,
            "tech_stack": item.get("detected_tech_stack") or ["SaaS"],
            "hiring_intent": bool(item.get("hiring_intent")),
            "intent_score": csp._safe_int(item.get("intent_score"), 65),
            "source_url": item.get("discussion_url") or item.get("source_url") or "",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "source_engine": "apify:b2b-intent-leads-ppe",
        })
    return out


# ---------------------------------------------------------------------------
# 1. PRODUCTIZED B2B AGENCY LEAD PACK GENERATOR
# ---------------------------------------------------------------------------
def generate_b2b_agency_pack(
    limit: int = 200,
    niche: str = "all",
    use_apify: bool = False,
    apify_token: str = "",
    output_dir: str | None = None,
    save: bool = True,
) -> dict:
    """Compile a productized CSV/JSON B2B lead pack (plus 5-row email sample) from live startup & hiring feeds."""
    target_limit = max(1, min(500, int(limit or 200)))
    niche_norm = (niche or "all").lower().strip()
    leads_by_key: dict[str, dict] = {}
    seen_headlines: set[str] = set()

    def _add(row: dict):
        if not row or not row.get("company_name"):
            return
        co_clean = row["company_name"].strip()
        if not co_clean or co_clean.startswith((">", "Because ", "Is ", "It's ")):
            return
        head_sig = re.sub(r"[^a-z0-9]+", "", (row.get("launch_headline") or "").lower())[:48]
        if head_sig and head_sig in seen_headlines:
            return
        dom = (row.get("domain") or "").lower().strip()
        if dom in ("", "unknown", "en.wikipedia.org", "wikipedia.org", "tradingeconomics.com") and not row.get("contact_email"):
            return
        if "ai manus" in (row.get("launch_headline") or "").lower():
            return
        if not _matches_niche_filter(niche_norm, row):
            return
        co = re.sub(r"[^a-z0-9]+", "", co_clean.lower())
        key = dom if (dom and dom not in GENERIC_SITE_BLOCKLIST and dom != "unknown") else f"{row.get('source_engine', 'live')}:{co}"
        if not key:
            return
        existing = leads_by_key.get(key)
        if not existing:
            leads_by_key[key] = row
            if head_sig:
                seen_headlines.add(head_sig)
        elif not existing.get("contact_email") and row.get("contact_email"):
            existing["contact_email"] = row["contact_email"]

    if use_apify and apify_token:
        try:
            for item in _fetch_apify_b2b_leads(target_limit, niche_norm, apify_token):
                _add(item)
        except Exception:
            pass

    # Merge fresh compiled B2B drop (Show HN, HN Jobs, Who Is Hiring, Remotive, GitHub launches)
    if len(leads_by_key) < target_limit:
        raw_pack = csp.compile_b2b_startup_leads(target_count=max(target_limit * 2, 250))
        for item in raw_pack.get("leads") or []:
            headline = item.get("launch_headline") or ""
            stack = item.get("tech_stack") or []
            _add({
                "company_name": item.get("company_name"),
                "niche_segment": _classify_niche(f"{headline} {' '.join(stack)}"),
                "domain": item.get("domain") or "unknown",
                "website_url": item.get("website_url") or "",
                "launch_headline": headline,
                "decision_maker": item.get("founder_or_contact"),
                "contact_email": item.get("email"),
                "tech_stack": stack,
                "hiring_intent": bool(item.get("hiring_intent")),
                "intent_score": csp._safe_int(item.get("intent_score"), 60),
                "source_url": item.get("source_url") or "",
                "published_at": item.get("published_at") or "",
                "source_engine": f"live:{item.get('source_type', 'hn')}",
            })

    # Add fresh Product Hunt launches
    if len(leads_by_key) < target_limit + 25:
        for ph in fetch_producthunt_launches(limit=25):
            _add({
                "company_name": ph["company_name"],
                "niche_segment": _classify_niche(ph["launch_headline"]),
                "domain": "producthunt.com",
                "website_url": ph["ph_url"],
                "launch_headline": ph["launch_headline"],
                "decision_maker": ph["maker"],
                "contact_email": None,
                "tech_stack": csp._infer_tech_stack(ph["launch_headline"]),
                "hiring_intent": False,
                "intent_score": 76,
                "source_url": ph["ph_url"],
                "published_at": ph["published_at"],
                "source_engine": "live:producthunt_feed",
            })

    # Add Remotive marketing/sales active hirers (prime B2B/agency buyers)
    if len(leads_by_key) < target_limit + 40:
        for cat in ("marketing", "sales"):
            try:
                rem = csp.fetch_json(f"https://remotive.com/api/remote-jobs?category={cat}&limit=40", timeout=8)
                for j in rem.get("jobs") or []:
                    co = csp._clean_text(j.get("company_name") or "")[:48]
                    if not co:
                        continue
                    title = csp._clean_text(j.get("title") or "")
                    _add({
                        "company_name": co,
                        "niche_segment": _classify_niche(f"{co} {title} {cat}"),
                        "domain": "remotive.com",
                        "website_url": j.get("url") or "",
                        "launch_headline": f"Hiring ({cat}): {title}"[:160],
                        "decision_maker": j.get("candidate_required_location") or "Remote",
                        "contact_email": None,
                        "tech_stack": (j.get("tags") or [])[:5] or [cat.capitalize()],
                        "hiring_intent": True,
                        "intent_score": 82,
                        "source_url": j.get("url") or "",
                        "published_at": j.get("publication_date") or "",
                        "source_engine": f"live:remotive_{cat}",
                    })
            except Exception:
                continue

    ranked = list(leads_by_key.values())
    ranked.sort(
        key=lambda r: (
            bool(r.get("contact_email")) and (r.get("domain") or "unknown") not in GENERIC_SITE_BLOCKLIST,
            bool(r.get("contact_email")),
            bool(r.get("hiring_intent")),
            (r.get("domain") or "unknown") not in GENERIC_SITE_BLOCKLIST,
            csp._safe_int(r.get("intent_score")),
        ),
        reverse=True,
    )
    selected = ranked[:target_limit]

    # Optionally enrich first 8 direct-domain websites for public business contact emails if sparse
    direct_email_candidates = [
        r for r in selected
        if not r.get("contact_email")
        and (r.get("website_url") or "").startswith("http")
        and (r.get("domain") or "unknown") not in GENERIC_SITE_BLOCKLIST
    ][:8]
    if direct_email_candidates:
        with ThreadPoolExecutor(max_workers=6) as pool:
            contacts = list(pool.map(lambda r: extract_business_contact_from_site(r["website_url"]), direct_email_candidates))
        for rec, cinfo in zip(direct_email_candidates, contacts):
            if cinfo.get("email"):
                rec["contact_email"] = cinfo["email"]

    report = {
        "pack_type": "agency_b2b_intent_leads",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "niche_filter": niche_norm,
        "requested_limit": target_limit,
        "total_leads": len(selected),
        "verified_email_count": sum(1 for r in selected if r.get("contact_email")),
        "hiring_intent_count": sum(1 for r in selected if r.get("hiring_intent")),
        "sample_5_preview": selected[:5],
        "leads": selected,
    }

    if save:
        out_dir = output_dir or DELIVERABLES_DIR
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(out_dir, f"agency_b2b_pack_{niche_norm}_{stamp}.json")
        csv_path = os.path.join(out_dir, f"agency_b2b_pack_{niche_norm}_{stamp}.csv")
        latest_csv = os.path.join(out_dir, "latest_agency_b2b_pack.csv")

        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(report, jf, indent=2)

        cols = [
            "company_name", "niche_segment", "domain", "website_url", "launch_headline",
            "decision_maker", "contact_email", "tech_stack", "hiring_intent",
            "intent_score", "source_url", "published_at", "source_engine",
        ]
        for path in (csv_path, latest_csv):
            with open(path, "w", encoding="utf-8", newline="") as cf:
                writer = csv.writer(cf)
                writer.writerow(cols)
                for r in selected:
                    writer.writerow([
                        r.get("company_name") or "",
                        r.get("niche_segment") or "",
                        r.get("domain") or "",
                        r.get("website_url") or "",
                        r.get("launch_headline") or "",
                        r.get("decision_maker") or "",
                        r.get("contact_email") or "",
                        " | ".join(r.get("tech_stack") or []),
                        str(bool(r.get("hiring_intent"))).lower(),
                        r.get("intent_score") or 0,
                        r.get("source_url") or "",
                        r.get("published_at") or "",
                        r.get("source_engine") or "",
                    ])

        report["artifacts"] = {"json": json_path, "csv": csv_path, "latest_csv": latest_csv}

    return report


# ---------------------------------------------------------------------------
# 2. E-COMMERCE COMPETITOR PRICE & STOCK MATRIX GENERATOR
# ---------------------------------------------------------------------------
def _discover_shopify_store_urls(store_url: str, max_items: int = 5) -> list[str]:
    try:
        parsed = urllib.parse.urlparse(store_url)
        if not parsed.scheme or not parsed.netloc:
            return []
        origin = f"{parsed.scheme}://{parsed.netloc}"
        data = csp.fetch_json(f"{origin}/products.json?limit={max_items}", timeout=6)
        products = data.get("products") or []
        return [f"{origin}/products/{p['handle']}" for p in products if isinstance(p, dict) and p.get("handle")][:max_items]
    except Exception:
        return []


def _fetch_live_ecom_product(target_url: str) -> dict:
    try:
        q = urllib.parse.quote(target_url, safe="")
        res = csp.fetch_json(f"{STORE_BASE_URL}/v1/preview/ecom-price-stock?url={q}", timeout=10)
        return {
            "url": target_url,
            "domain": urllib.parse.urlparse(target_url).netloc.lower().removeprefix("www."),
            "status": "ok" if res.get("status") == "success" else "error",
            "title": res.get("title") or "",
            "price": csp._safe_float(res.get("price"), default=0.0),
            "currency": res.get("currency") or "USD",
            "in_stock": bool(res.get("in_stock")),
            "sku": res.get("sku") or "",
            "platform": res.get("platform") or "",
            "error": None,
        }
    except Exception as exc:
        return {
            "url": target_url,
            "domain": urllib.parse.urlparse(target_url).netloc.lower().removeprefix("www.") if target_url.startswith("http") else "",
            "status": "error",
            "title": "",
            "price": None,
            "currency": "",
            "in_stock": None,
            "sku": "",
            "platform": "",
            "error": str(exc),
        }


def generate_ecom_competitor_matrix(
    anchor_url: str,
    competitor_urls: list[str] | None = None,
    max_competitors: int = 5,
    output_dir: str | None = None,
    save: bool = True,
) -> dict:
    """Pull real-time prices, stock booleans & price deltas vs anchor store across competitor product URLs."""
    comp_list = [u.strip() for u in (competitor_urls or []) if u and u.strip()][:max_competitors]

    target_urls = []
    if anchor_url and "/products/" not in anchor_url and not comp_list:
        discovered = _discover_shopify_store_urls(anchor_url, max_items=max_competitors + 1)
        target_urls.extend(discovered)
    if not target_urls and anchor_url:
        target_urls = [anchor_url.strip()] + comp_list
    elif comp_list:
        target_urls.extend(comp_list)

    target_urls = list(dict.fromkeys(target_urls))
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(_fetch_live_ecom_product, target_urls))

    anchor_row = rows[0] if rows else None
    anchor_price = anchor_row.get("price") if (anchor_row and anchor_row.get("status") == "ok") else None

    for idx, r in enumerate(rows):
        r["role"] = "anchor" if idx == 0 else f"competitor_{idx}"
        if idx > 0 and anchor_price and anchor_price > 0 and r.get("price") is not None:
            delta = round(r["price"] - anchor_price, 2)
            r["price_delta"] = delta
            r["delta_pct"] = round((delta / anchor_price) * 100.0, 2)
        else:
            r["price_delta"] = 0.0 if idx == 0 else None
            r["delta_pct"] = 0.0 if idx == 0 else None

    matrix = {
        "pack_type": "ecom_competitor_price_matrix",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anchor_url": anchor_url,
        "total_checked": len(rows),
        "live_verified_count": sum(1 for r in rows if r.get("status") == "ok"),
        "rows": rows,
    }

    if save:
        out_dir = output_dir or DELIVERABLES_DIR
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(out_dir, f"ecom_competitor_matrix_{stamp}.json")
        csv_path = os.path.join(out_dir, f"ecom_competitor_matrix_{stamp}.csv")
        latest_csv = os.path.join(out_dir, "latest_ecom_matrix.csv")

        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(matrix, jf, indent=2)

        cols = ["role", "domain", "title", "price", "currency", "in_stock", "price_delta", "delta_pct", "sku", "platform", "status", "url"]
        for path in (csv_path, latest_csv):
            with open(path, "w", encoding="utf-8", newline="") as cf:
                w = csv.writer(cf)
                w.writerow(cols)
                for r in rows:
                    w.writerow([r.get(c) if r.get(c) is not None else "" for c in cols])

        matrix["artifacts"] = {"json": json_path, "csv": csv_path, "latest_csv": latest_csv}

    return matrix


def format_b2b_sample_block(leads: list[dict], limit: int = 5) -> str:
    subset = (leads or [])[:limit]
    if not subset:
        return ""
    lines = ["Free 5-row live B2B intent sample pulled right now:"]
    for idx, r in enumerate(subset, 1):
        tag_str = ", ".join((r.get("tech_stack") or [])[:3])
        email_note = f" | Contact: {r['contact_email']}" if r.get("contact_email") else ""
        lines.append(
            f"{idx}. {r['company_name']} ({r['domain']}) — {r['launch_headline'][:80]} [{tag_str}; Intent {r['intent_score']}/100{email_note}]"
        )
    return "\n".join(lines) + "\n"


def format_ecom_matrix_block(rows: list[dict], limit: int = 4) -> str:
    ok_rows = [r for r in (rows or []) if r.get("status") == "ok"][:limit]
    if not ok_rows:
        return ""
    lines = ["Live E-Commerce Price & Stock Check (via AgentFuel402 E-Com Engine):"]
    for idx, r in enumerate(ok_rows, 1):
        stock = "IN STOCK" if r.get("in_stock") else "OUT OF STOCK"
        delta_note = f" ({r['delta_pct']:+.1f}% vs anchor)" if r.get("delta_pct") not in (None, 0.0) else ""
        lines.append(f"{idx}. {r['title'][:48]} ({r['domain']}): {r['price']} {r['currency']} [{stock}]{delta_note}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 3. HIGH-TICKET BUSINESS BUYER OUTBOUND & FREE AUDIT LEAD MAGNETS
# ---------------------------------------------------------------------------
def run_buyer_lead_magnet_audit(prospect: dict, sample_leads: list[dict] | None = None, timeout: int = 5) -> str:
    """Run a real live free audit / sample tailored to the prospect's business segment."""
    segment = prospect.get("segment") or "segment_agency"
    website = (prospect.get("website_url") or prospect.get("homepage") or "").strip()

    if segment == "segment_ai_saas":
        sample_txt = (prospect.get("site_excerpt") or prospect.get("context_desc") or prospect.get("company") or "").strip()
        if sample_txt:
            try:
                res = _http_post_json(
                    "https://canaryguard-402.onrender.com/v1/sanitize/preview",
                    {"content": sample_txt[:2500], "strict_mode": True},
                    timeout=timeout,
                )
                threats = res.get("threats_neutralized") or []
                return (
                    f"Free CanaryGuard automated check on {website or prospect.get('company')}: "
                    f"status={res.get('status', 'clean')} in {res.get('engine_ms', '<10')} ms "
                    f"({len(threats)} rule trigger(s); checks prompt overrides, zero-width smuggling & key leaks)."
                )
            except Exception:
                pass
        return ""

    if segment == "segment_ecom":
        product_urls = []
        if website.startswith(("http://", "https://")):
            if "/products/" in website:
                product_urls = [website]
            else:
                product_urls = _discover_shopify_store_urls(website, max_items=3)
        if product_urls:
            matrix = generate_ecom_competitor_matrix(product_urls[0], competitor_urls=product_urls[1:], save=False)
            block = format_ecom_matrix_block(matrix.get("rows"), limit=3)
            if block:
                return block
        # Fallback clearly labeled as a live sample WooCommerce benchmark
        bench = generate_ecom_competitor_matrix(
            "https://scrapeme.live/shop/Bulbasaur/",
            competitor_urls=["https://scrapeme.live/shop/Charmander/", "https://scrapeme.live/shop/Squirtle/"],
            save=False,
        )
        block = format_ecom_matrix_block(bench.get("rows"), limit=3)
        return block.replace(
            "Live E-Commerce Price & Stock Check (via AgentFuel402 E-Com Engine):",
            "Live sample demo from our E-Com Price & Stock Engine (live benchmark store):",
        ) if block else ""

    # segment_agency: attach 5 freshly pulled live B2B intent leads
    return format_b2b_sample_block(sample_leads or [], limit=5)


def discover_business_buyers(
    segment: str,
    limit: int = 2,
    exclude_emails: set | None = None,
    exclude_users: set | None = None,
    gh_token: str = "",
    email_validator=None,
) -> list[dict]:
    """
    Discover real high-intent commercial buyers across 3 segments:
      - segment_agency: Digital marketing, lead-gen & workflow automation agencies
      - segment_ecom: Shopify / WooCommerce brand builders & e-commerce stores
      - segment_ai_saas: Founders launching new AI / SaaS products on Product Hunt / Show HN
    Requires deliverable MX-verified email + business/commercial signal.
    """
    excl_emails = set(exclude_emails or ())
    excl_users = set(exclude_users or ())
    gh_tok = gh_token or csp.resolve_gh_token()
    gh_hdrs = {"Accept": "application/vnd.github.v3+json"}
    if gh_tok:
        gh_hdrs["Authorization"] = f"Bearer {gh_tok}"

    def _email_ok(cand: str | None) -> str | None:
        if not cand or "@" not in cand:
            return None
        em = cand.lower().strip()
        if em in excl_emails:
            return None
        if email_validator is not None and not email_validator(em):
            return None
        return em

    found = []

    if segment == "segment_ai_saas":
        # 1. Product Hunt Atom launches -> resolve direct site & public contact email
        for ph in fetch_producthunt_launches(limit=15):
            if len(found) >= limit:
                break
            site = _resolve_redirect_url(ph.get("redirect_url") or "")
            if not site or "producthunt.com" in site:
                continue
            info = extract_business_contact_from_site(site, email_validator=email_validator)
            em = _email_ok(info.get("email"))
            if not em:
                continue
            excl_emails.add(em)
            found.append({
                "segment": "segment_ai_saas",
                "lead_source": "producthunt_launch",
                "username": (ph.get("maker") or ph["company_name"]).lower().replace(" ", "_")[:30],
                "name": ph.get("maker") or ph["company_name"],
                "company": ph["company_name"],
                "email": em,
                "website_url": site,
                "site_excerpt": info.get("text_excerpt") or ph["launch_headline"],
                "context_desc": ph["launch_headline"],
                "repo": site,
            })

        # 2. Show HN & recent AI/SaaS launches
        if len(found) < limit:
            try:
                hits = csp.fetch_json("https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&hitsPerPage=35", timeout=8).get("hits") or []
                for h in hits:
                    if len(found) >= limit:
                        break
                    site = (h.get("url") or "").strip()
                    title = csp._clean_text(h.get("title") or "")
                    story_txt = csp._clean_text(h.get("story_text") or "")
                    em = _email_ok(csp.extract_public_email(story_txt))
                    site_excerpt = title
                    if not em and site.startswith("http"):
                        info = extract_business_contact_from_site(site, email_validator=email_validator)
                        em = _email_ok(info.get("email"))
                        site_excerpt = info.get("text_excerpt") or title
                    if not em:
                        continue
                    excl_emails.add(em)
                    raw_co = re.split(r"\s+[–—\-|:]\s+|:\s+", re.sub(r"^(?:Show HN|Launch HN):\s*", "", title, flags=re.I), maxsplit=1)[0].strip()
                    host_brand = ""
                    if site.startswith("http"):
                        try:
                            host_brand = urllib.parse.urlparse(site).netloc.lower().removeprefix("www.").split(".")[0].capitalize()
                        except Exception:
                            pass
                    if not raw_co or len(raw_co.split()) > 3 or raw_co.lower().startswith(("i ", "we ", "my ", "a ", "the ", "building ", "how ")):
                        co = host_brand or raw_co[:32] or "Your SaaS"
                    else:
                        co = raw_co[:42]
                    found.append({
                        "segment": "segment_ai_saas",
                        "lead_source": "show_hn_launch",
                        "username": (h.get("author") or co).lower()[:30],
                        "name": h.get("author") or co,
                        "company": co or "Your SaaS",
                        "email": em,
                        "website_url": site or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                        "site_excerpt": site_excerpt,
                        "context_desc": title,
                        "repo": site or co,
                    })
            except Exception:
                pass
        return found[:limit]

    # GitHub + Website lookup for Boutique Agencies & E-Commerce Stores / Builders
    if segment == "segment_agency":
        queries = [
            '"digital agency" OR "marketing agency" website stars:1..150',
            '"lead generation" agency OR outreach stars:1..150',
            '"n8n" agency OR automation workflow stars:1..150',
        ]
    else:  # segment_ecom
        queries = [
            '"shopify" storefront OR theme OR wholesale stars:1..200',
            '"woocommerce" store OR retail OR catalog stars:1..200',
            '"shopify" "price tracker" OR inventory stars:1..200',
        ]

    for q in queries:
        if len(found) >= limit:
            break
        try:
            url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(q)}&sort=updated&order=desc&per_page=15"
            items = csp.fetch_json(url, timeout=8, headers=gh_hdrs).get("items") or []
            for repo in items:
                if len(found) >= limit:
                    break
                if repo.get("fork") or repo.get("archived"):
                    continue
                owner = ((repo.get("owner") or {}).get("login") or "").strip()
                norm_u = owner.lower()
                if not owner or norm_u in excl_users or "[bot]" in norm_u:
                    continue
                try:
                    u_meta = csp.fetch_json(f"https://api.github.com/users/{urllib.parse.quote(owner)}", timeout=5, headers=gh_hdrs)
                except Exception:
                    continue
                if (u_meta.get("type") or "").lower() == "bot":
                    continue
                homepage = (repo.get("homepage") or u_meta.get("blog") or "").strip()
                if homepage and not homepage.startswith(("http://", "https://")):
                    homepage = f"https://{homepage}"

                em = _email_ok(u_meta.get("email"))
                site_info = {"title": "", "text_excerpt": ""}
                if not em and homepage.startswith("http"):
                    site_info = extract_business_contact_from_site(homepage, email_validator=email_validator)
                    em = _email_ok(site_info.get("email"))
                if not em:
                    continue

                excl_emails.add(em)
                excl_users.add(norm_u)
                host_brand = ""
                if homepage.startswith(("http://", "https://")):
                    try:
                        h_dom = urllib.parse.urlparse(homepage).netloc.lower().removeprefix("www.")
                        if h_dom and h_dom not in GENERIC_SITE_BLOCKLIST:
                            host_brand = h_dom
                    except Exception:
                        pass
                co_name = csp._clean_text(u_meta.get("company") or host_brand or repo.get("name") or owner).lstrip("@").strip()
                found.append({
                    "segment": segment,
                    "lead_source": "agency_org_search" if segment == "segment_agency" else "ecom_brand_search",
                    "username": owner,
                    "name": csp._clean_text(u_meta.get("name") or owner),
                    "company": co_name[:48],
                    "email": em,
                    "website_url": homepage or repo.get("html_url") or "",
                    "homepage": homepage,
                    "site_excerpt": site_info.get("text_excerpt") or "",
                    "context_desc": csp._clean_text(repo.get("description") or co_name)[:140],
                    "repo": repo.get("full_name") or owner,
                })
        except Exception:
            continue

    return found[:limit]


def craft_high_ticket_pitch(prospect: dict, audit_summary: str = "") -> tuple[str, str]:
    """Craft zero-micro-pricing high-ticket Agency Arbitrage or Free Audit lead-magnet emails."""
    raw_name = (prospect.get("name") or "").strip()
    username = (prospect.get("username") or "").strip()
    cand_first = raw_name.split()[0] if raw_name else ""
    if (
        cand_first
        and cand_first.lower() != username.lower()
        and re.fullmatch(r"[A-Za-z][A-Za-z\-']{1,18}", cand_first)
    ):
        first = cand_first
    else:
        email_local = (prospect.get("email") or "").split("@")[0].split(".")[0]
        if email_local and re.fullmatch(r"[A-Za-z]{2,12}", email_local) and email_local.lower() not in {"hello", "founders", "contact", "team", "admin", "info", "support", "sales"}:
            first = email_local.capitalize()
        else:
            first = "there"
    company = (prospect.get("company") or prospect.get("repo") or "your team").strip()
    segment = prospect.get("segment") or "segment_agency"
    audit_block = f"{audit_summary.strip()}\n\n" if (audit_summary or "").strip() else ""

    if segment == "segment_ecom":
        subject = f"Free competitor price & stock check for {company}"[:68]
        body = (
            f"Hey {first},\n\n"
            f"Quick zero-pitch note — noticed you're scaling {company} in e-commerce.\n\n"
            f"{audit_block}"
            f"If you'd like me to run a free live pricing & out-of-stock matrix across your top 3 competitors, just reply with their URLs and I'll send the CSV over.\n\n"
            f"Whenever you want the full automated 20-competitor price tracker or a custom 200-lead store pack ($149 USD flat via Stripe or USDC):\n"
            f"{STRIPE_AGENCY_PACK_URL}\n"
            f"Storefront & self-serve packs: {STORE_URL}\n\n"
            f"Best,\nArman\n"
        )
        return subject, body

    if segment == "segment_ai_saas":
        subject = f"Free AI prompt-injection check for {company}"[:68]
        body = (
            f"Hey {first},\n\n"
            f"Congrats on launching {company} — sharing a quick automated security check we ran (zero pitch):\n\n"
            f"{audit_block}"
            f"If you want the full verifiable Security Audit Certificate + README badge ($9.99 one-time) or a 90-day API pass ($19) for CanaryGuard prompt-injection protection:\n"
            f"Storefront & Instant Certificate: {STORE_URL}\n"
            f"Pro 90-day Stripe Checkout ($19): {STRIPE_PRO_KEY_URL}\n\n"
            f"Happy to answer anything over email — no calls needed.\n\n"
            f"Best,\nArman\n"
        )
        return subject, body

    # segment_agency
    subject = f"5 freshly funded B2B intent leads for {company}"[:68]
    body = (
        f"Hey {first},\n\n"
        f"Saw you're running {company}. We built an automated intent pipeline that tracks newly launched & actively hiring AI/SaaS companies without stale Apollo/ZoomInfo lists. I pulled a free 5-row live sample for you below:\n\n"
        f"{audit_block}"
        f"Two fast ways to grab full drops with zero recurring subscription:\n"
        f"1) Custom 200-lead niche CSV pack ($149 flat via Stripe or USDC):\n"
        f"{STRIPE_AGENCY_PACK_URL}\n"
        f"2) Instant 500-lead Store drop ($39) or bulk Apify batch run:\n"
        f"{STORE_URL}\n"
        f"https://apify.com/kuroxreal/b2b-intent-leads-ppe\n\n"
        f"Reply with your target niche if you want a custom 5-lead sample run before ordering.\n\n"
        f"Best,\nArman\n"
    )
    return subject, body


def _print_b2b_report(report: dict):
    print("=============================================================================")
    print("AGENTFUEL402 — PRODUCTIZED B2B AGENCY LEAD PACK")
    print(f"Generated: {report['generated_at']} | Niche: {report['niche_filter']}")
    print(f"Total Leads: {report['total_leads']} | Published Emails: {report['verified_email_count']} | Hiring: {report['hiring_intent_count']}")
    if report.get("artifacts"):
        print(f"CSV Saved:   {report['artifacts']['csv']}")
        print(f"JSON Saved:  {report['artifacts']['json']}")
    print("-----------------------------------------------------------------------------")
    for idx, row in enumerate(report.get("leads") or [], 1):
        em = f" | Email: {row['contact_email']}" if row.get("contact_email") else ""
        tags = ", ".join((row.get("tech_stack") or [])[:3])
        print(f"{idx:2}. {row['company_name']} ({row['domain']}) [{row['niche_segment']}] — Intent {row['intent_score']}/100{em}")
        print(f"    Headline: {row['launch_headline'][:100]} | Stack: {tags}")
    print("\n--- EMAIL-READY 5-ROW OUTREACH SAMPLE PREVIEW ---")
    print(format_b2b_sample_block(report.get("sample_5_preview") or [], limit=5))


def _print_ecom_matrix(matrix: dict):
    print("=============================================================================")
    print("AGENTFUEL402 — E-COMMERCE COMPETITOR PRICE & STOCK MATRIX")
    print(f"Generated: {matrix['generated_at']} | Anchor: {matrix['anchor_url']}")
    print(f"Checked: {matrix['total_checked']} | Live Verified: {matrix['live_verified_count']}")
    if matrix.get("artifacts"):
        print(f"CSV Saved:  {matrix['artifacts']['csv']}")
        print(f"JSON Saved: {matrix['artifacts']['json']}")
    print("-----------------------------------------------------------------------------")
    for r in matrix.get("rows") or []:
        delta_s = f" | Delta: {r['price_delta']:+.2f} ({r['delta_pct']:+.1f}%)" if r.get("delta_pct") is not None else ""
        print(f"- [{r['role']}] {r['title'] or r['url']}: {r['price']} {r['currency']} | in_stock={r['in_stock']}{delta_s}")


def main():
    parser = argparse.ArgumentParser(description="AgentFuel402 Agency Arbitrage & Productized Data Pack Engine")
    parser.add_argument("--mode", choices=["b2b-pack", "ecom-matrix", "dry-run-buyers"], default="b2b-pack")
    parser.add_argument("--limit", type=int, default=200, help="Number of B2B leads to compile (1-500, default: 200)")
    parser.add_argument("--niche", default="all", choices=["all", "ai", "saas", "ecommerce", "agency"], help="Niche filter for B2B packs")
    parser.add_argument("--use-apify", action="store_true", help="Include live Apify Actor run when APIFY_TOKEN is set")
    parser.add_argument("--anchor-url", default="https://scrapeme.live/shop/Bulbasaur/", help="Anchor product/store URL for ecom-matrix")
    parser.add_argument("--competitors", default="", help="Comma-separated competitor product URLs for ecom-matrix")
    parser.add_argument("--no-save", action="store_true", help="Do not write CSV/JSON files to data/deliverables/")
    args = parser.parse_args()

    apify_tok = (os.environ.get("APIFY_TOKEN") or "").strip()

    if args.mode == "b2b-pack":
        report = generate_b2b_agency_pack(
            limit=args.limit,
            niche=args.niche,
            use_apify=args.use_apify,
            apify_token=apify_tok,
            save=not args.no_save,
        )
        _print_b2b_report(report)
        return

    if args.mode == "ecom-matrix":
        comps = [u.strip() for u in args.competitors.split(",") if u.strip()]
        if not comps and args.anchor_url == "https://scrapeme.live/shop/Bulbasaur/":
            comps = ["https://scrapeme.live/shop/Charmander/", "https://scrapeme.live/shop/Squirtle/"]
        matrix = generate_ecom_competitor_matrix(args.anchor_url, competitor_urls=comps, save=not args.no_save)
        _print_ecom_matrix(matrix)
        return

    sample = generate_b2b_agency_pack(limit=5, save=False).get("leads") or []
    for seg in ("segment_agency", "segment_ecom", "segment_ai_saas"):
        print(f"\n=== BUYER SEGMENT DRY RUN: {seg} ===")
        buyers = discover_business_buyers(seg, limit=1)
        for b in buyers:
            audit = run_buyer_lead_magnet_audit(b, sample_leads=sample)
            subj, body = craft_high_ticket_pitch(b, audit_summary=audit)
            print(f"To: {b['email']} | Company: {b['company']} | URL: {b['website_url']}")
            print(f"Subject: {subj}\n{body}")


if __name__ == "__main__":
    main()
