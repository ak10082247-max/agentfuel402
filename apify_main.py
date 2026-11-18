"""
AgentFuel402 — Apify Pay-Per-Event (PPE) Execution Engine
Verify -> Fetch -> Settle Architecture (Never Charge for Failed Upstream Targets)
Publishes billable PPE events only on valid extracted data:
1. lead-signal-fetch ($0.010 USD)
2. clean-markdown-fetch ($0.003 USD)
3. ecom-product-check ($0.003 USD)
4. reverse-engineer-target ($0.015 USD)
"""
import asyncio
from datetime import datetime, timedelta, timezone
import os
import re
import time
from urllib.parse import quote_plus
from apify import Actor
import httpx
from bs4 import BeautifulSoup

MAX_B2B_LEADS = 500
DEFAULT_B2B_LEADS = 50
MAX_BATCH_URLS = 100
SHARED_HOST_DOMAINS = {
    "github.com",
    "news.ycombinator.com",
    "linkedin.com",
    "x.com",
    "twitter.com",
    "youtube.com",
    "medium.com",
    "substack.com",
    "unknown",
    "",
}


def sanitize_prompt(text: str) -> str:
    clean = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
    clean = re.sub(r"\b(ignore\s+(all\s+)?(previous|prior)\s+instructions)\b", "[SANITIZED: PROMPT_INJECTION_OVERRIDE]", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(system\s+prompt|system\s*:\s*you\s+are)\b", "[SANITIZED: SYSTEM_PROMPT_SPOOF]", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(jailbreak|DAN\s+mode|unrestricted\s+ai|do\s+anything\s+now)\b", "[SANITIZED: JAILBREAK_PATTERN]", clean, flags=re.IGNORECASE)
    return clean


def _extract_host(url: str) -> str:
    if not url:
        return "unknown"
    try:
        host = (httpx.URL(url).host or "").lower().strip()
        if host.startswith("www."):
            host = host[4:]
        return host or "unknown"
    except Exception:
        return "unknown"


def _detect_tech_stack(text_blob: str) -> list:
    lower = (text_blob or "").lower()
    tags = []
    if any(k in lower for k in ("ai", "llm", "agent", "openai", "anthropic", "rag", "ml")):
        tags.append("AI/LLM")
    if any(k in lower for k in ("react", "next.js", "nextjs", "typescript", "node")):
        tags.append("TypeScript/React")
    if any(k in lower for k in ("python", "fastapi", "django", "pytorch")):
        tags.append("Python")
    if any(k in lower for k in ("shopify", "woocommerce", "ecommerce", "e-commerce", "checkout")):
        tags.append("E-Commerce")
    if any(k in lower for k in ("rust", "go ", "golang")):
        tags.append("Systems/Rust/Go")
    if any(k in lower for k in ("postgres", "database", "sql", "redis", "clickhouse")):
        tags.append("Database")
    return tags or ["SaaS", "Developer Tools"]


def _matches_lead_category(category: str, lead: dict, text_blob: str = "") -> bool:
    cat = (category or "all").lower().strip()
    if not cat or cat == "all":
        return True
    hay = f"{lead.get('company_name', '')} {lead.get('launch_headline', '')} {' '.join(lead.get('detected_tech_stack', []))} {text_blob}".lower()
    cat_keywords = {
        "ai": ("ai", "llm", "agent", "rag", "ml", "openai", "anthropic", "gpt", "claude"),
        "devtools": ("api", "sdk", "cli", "devtools", "developer", "github", "mcp", "database", "typescript", "python", "rust"),
        "saas": ("saas", "b2b", "crm", "workflow", "automation", "analytics", "platform", "hiring"),
        "ecommerce": ("ecommerce", "e-commerce", "shopify", "woocommerce", "retail", "store", "commerce", "checkout"),
    }
    return any(tok in hay for tok in cat_keywords.get(cat, (cat,)))


def _build_lead_record(
    company_name: str,
    headline: str,
    source_url: str,
    discussion_url: str,
    author: str,
    score: int,
    comments: int,
    hiring: bool,
    tech_tags: list,
    source_feed: str,
) -> dict:
    domain = _extract_host(source_url)
    intent_score = min(100, max(30, int(score or 1) * 2 + int(comments or 0) * 3 + (20 if hiring else 0)))
    signals = [
        f"Verified live commercial signal via {source_feed}",
        "Active talent acquisition footprint" if hiring else "Community/launch engagement spike",
        f"Intent Score: {intent_score}/100 based on founder momentum and activity",
    ]
    return {
        "company_name": (company_name or "Startup")[:120],
        "launch_headline": (headline or company_name or "Startup Launch")[:240],
        "domain": domain,
        "source_url": source_url or discussion_url,
        "discussion_url": discussion_url or source_url,
        "author": author or "founder",
        "score": int(score or 1),
        "comments_count": int(comments or 0),
        "detected_tech_stack": tech_tags,
        "hiring_intent": bool(hiring),
        "intent_score": intent_score,
        "estimated_stage": "Seed/Series A" if (score or 0) > 80 or hiring else "Early Stage / Pre-Seed",
        "source_feed": source_feed,
        "signals": signals,
    }


async def run_b2b_leads(limit=DEFAULT_B2B_LEADS, category="all"):
    target_limit = max(1, min(MAX_B2B_LEADS, int(limit or DEFAULT_B2B_LEADS)))
    cat = (category or "all").lower().strip()
    leads = []
    seen_keys = set()

    def try_add(lead: dict, raw_blob: str = "") -> bool:
        if not lead or not lead.get("company_name"):
            return False
        if not _matches_lead_category(cat, lead, raw_blob):
            return False
        comp_key = re.sub(r"[^a-z0-9]+", "", lead["company_name"].lower())
        dom = (lead.get("domain") or "unknown").lower()
        src = (lead.get("source_url") or "").lower().split("?")[0]
        dedup_dom = dom if dom not in SHARED_HOST_DOMAINS else src
        if (comp_key and comp_key in seen_keys) or (dedup_dom and dedup_dom in seen_keys):
            return False
        if comp_key:
            seen_keys.add(comp_key)
        if dedup_dom:
            seen_keys.add(dedup_dom)
        leads.append(lead)
        return len(leads) >= target_limit

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        # 1. Primary multi-page HackerNews Algolia feeds (Show HN, Jobs, Ask HN)
        algolia_specs = []
        if cat != "all":
            algolia_specs.append(("show_hn", cat, 2))
        algolia_specs.extend([
            ("show_hn", None, 4 if target_limit > 50 else 1),
            ("job", None, 2 if target_limit > 50 else 1),
            ("ask_hn", "hiring", 2 if target_limit > 50 else 1),
        ])
        for tag, query, pages in algolia_specs:
            if len(leads) >= target_limit:
                break
            for page in range(pages):
                if len(leads) >= target_limit:
                    break
                try:
                    q_part = f"&query={quote_plus(query)}" if query else ""
                    algolia_url = f"https://hn.algolia.com/api/v1/search_by_date?tags={tag}{q_part}&hitsPerPage=100&page={page}"
                    res = await client.get(algolia_url, headers={"User-Agent": "AgentFuel402-B2B/2.0"})
                    if res.status_code != 200:
                        break
                    hits = res.json().get("hits", [])
                    if not hits:
                        break
                    for story in hits:
                        title = (story.get("title") or "").strip()
                        if not title:
                            continue
                        clean_title = re.sub(r"^(?:Show HN|Ask HN|Launch HN):\s*", "", title, flags=re.IGNORECASE).strip()
                        raw_url = (story.get("url") or "").strip()
                        disc_url = f"https://news.ycombinator.com/item?id={story.get('objectID')}"
                        blob = f"{title} {story.get('story_text') or ''}"
                        hiring = tag == "job" or any(w in blob.lower() for w in ("hiring", "is hiring", "yc", "careers", "job")) or (story.get("points") or 0) > 25
                        if tag == "job":
                            m_co = re.match(r"^([^(\n]+?)\s+(?:\(|is\s+hiring\b|hiring\b|-)", clean_title, re.IGNORECASE)
                            comp_name = m_co.group(1).strip() if m_co else clean_title.split(" is ")[0].split("(")[0].strip()
                        else:
                            comp_name = clean_title.split(" - ")[0].split(" — ")[0].split(":")[0].strip()
                        lead = _build_lead_record(
                            company_name=comp_name,
                            headline=clean_title,
                            source_url=raw_url or disc_url,
                            discussion_url=disc_url,
                            author=story.get("author") or "founder",
                            score=story.get("points") or 1,
                            comments=story.get("num_comments") or 0,
                            hiring=hiring,
                            tech_tags=_detect_tech_stack(blob),
                            source_feed=f"HN Algolia ({tag})",
                        )
                        if try_add(lead, blob):
                            break
                except Exception as e:
                    Actor.log.warning(f"Algolia {tag} page {page} failed: {e}")
                    break

        # 2. Remote Tech Job Boards (Arbeitnow & Remotive — actively hiring tech companies)
        if len(leads) < target_limit:
            for page in (1, 2, 3):
                if len(leads) >= target_limit:
                    break
                try:
                    res = await client.get(f"https://www.arbeitnow.com/api/job-board-api?page={page}", headers={"User-Agent": "AgentFuel402-B2B/2.0"})
                    if res.status_code != 200:
                        break
                    jobs = res.json().get("data") or []
                    if not jobs:
                        break
                    for job in jobs:
                        company = (job.get("company_name") or "").strip()
                        title = (job.get("title") or "").strip()
                        j_url = (job.get("url") or "").strip()
                        tags = job.get("tags") or []
                        blob = f"{company} {title} {' '.join(tags)} {job.get('description', '')[:400]}"
                        if not company or not j_url:
                            continue
                        lead = _build_lead_record(
                            company_name=company,
                            headline=f"{company} hiring {title}" if title else f"{company} remote hiring",
                            source_url=j_url,
                            discussion_url=j_url,
                            author=company,
                            score=30 if job.get("remote") else 20,
                            comments=len(tags),
                            hiring=True,
                            tech_tags=_detect_tech_stack(blob),
                            source_feed="Arbeitnow Job Board",
                        )
                        if try_add(lead, blob):
                            break
                except Exception as e:
                    Actor.log.warning(f"Arbeitnow fetch failed: {e}")
                    break

        if len(leads) < target_limit:
            try:
                res = await client.get("https://remotive.com/api/remote-jobs?limit=100", headers={"User-Agent": "AgentFuel402-B2B/2.0"})
                if res.status_code == 200:
                    for job in res.json().get("jobs") or []:
                        company = (job.get("company_name") or "").strip()
                        title = (job.get("title") or "").strip()
                        j_url = (job.get("url") or "").strip()
                        blob = f"{company} {title} {job.get('category', '')} {' '.join(job.get('tags') or [])}"
                        if not company or not j_url:
                            continue
                        lead = _build_lead_record(
                            company_name=company,
                            headline=f"{company} hiring {title}" if title else company,
                            source_url=j_url,
                            discussion_url=j_url,
                            author=company,
                            score=35,
                            comments=2,
                            hiring=True,
                            tech_tags=_detect_tech_stack(blob),
                            source_feed="Remotive Tech Jobs",
                        )
                        if try_add(lead, blob):
                            break
            except Exception as e:
                Actor.log.warning(f"Remotive fetch failed: {e}")

        # 3. GitHub Newly Created Commercial Orgs & SaaS/AI Launches (last 30 days)
        if len(leads) < target_limit:
            try:
                since_30d = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
                gh_q = f"created:>={since_30d} stars:>=5"
                if cat != "all":
                    gh_q = f"{cat} " + gh_q
                gh_headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "AgentFuel402-B2B/2.0"}
                gh_pat = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or ""
                if gh_pat:
                    gh_headers["Authorization"] = f"Bearer {gh_pat}"
                for page in (1, 2):
                    if len(leads) >= target_limit:
                        break
                    res = await client.get(
                        f"https://api.github.com/search/repositories?q={quote_plus(gh_q)}&sort=stars&order=desc&per_page=100&page={page}",
                        headers=gh_headers,
                    )
                    if res.status_code != 200:
                        break
                    items = res.json().get("items") or []
                    if not items:
                        break
                    for repo in items:
                        if repo.get("fork") or repo.get("archived"):
                            continue
                        homepage = (repo.get("homepage") or "").strip()
                        html_url = (repo.get("html_url") or "").strip()
                        owner_name = (repo.get("owner") or {}).get("login") or ""
                        desc = (repo.get("description") or "").strip()
                        topics = repo.get("topics") or []
                        blob = f"{repo.get('full_name', '')} {desc} {' '.join(topics)} {repo.get('language') or ''}"
                        lead = _build_lead_record(
                            company_name=owner_name or repo.get("name") or "GitHub Launch",
                            headline=desc or repo.get("full_name") or owner_name,
                            source_url=homepage if homepage.startswith(("http://", "https://")) else html_url,
                            discussion_url=html_url,
                            author=owner_name,
                            score=min(100, (repo.get("stargazers_count") or 5)),
                            comments=repo.get("open_issues_count") or 0,
                            hiring=False,
                            tech_tags=_detect_tech_stack(blob),
                            source_feed="GitHub New Launches (30d)",
                        )
                        if try_add(lead, blob):
                            break
            except Exception as e:
                Actor.log.warning(f"GitHub launches fetch failed: {e}")

        # 4. Firebase fallback if still empty
        if not leads:
            try:
                res = await client.get("https://hacker-news.firebaseio.com/v0/showstories.json")
                if res.status_code == 200:
                    for sid in res.json()[:target_limit]:
                        if len(leads) >= target_limit:
                            break
                        try:
                            s_res = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                            if s_res.status_code == 200:
                                s = s_res.json()
                                if not s or "title" not in s:
                                    continue
                                title = re.sub(r"^Show HN:\s*", "", s.get("title", ""), flags=re.IGNORECASE).strip()
                                raw_url = (s.get("url") or "").strip()
                                disc_url = f"https://news.ycombinator.com/item?id={sid}"
                                score = s.get("score", 1)
                                lead = _build_lead_record(
                                    company_name=title.split("-")[0].split(":")[0].strip(),
                                    headline=title,
                                    source_url=raw_url or disc_url,
                                    discussion_url=disc_url,
                                    author=s.get("by") or "founder",
                                    score=score,
                                    comments=s.get("descendants", 0),
                                    hiring=score > 30,
                                    tech_tags=_detect_tech_stack(title),
                                    source_feed="HN Firebase ShowStories",
                                )
                                try_add(lead, title)
                        except Exception:
                            pass
            except Exception as e:
                Actor.log.warning(f"Firebase fallback failed: {e}")

    if not leads:
        return {
            "status": "error",
            "error": "upstream_leads_unavailable",
            "event_name": "lead-signal-fetch",
            "feed": "/v1/fuel/b2b-intent-leads",
            "timestamp_ms": int(time.time() * 1000),
            "count": 0,
            "leads": []
        }

    return {
        "status": "success",
        "event_name": "lead-signal-fetch",
        "feed": "/v1/fuel/b2b-intent-leads",
        "timestamp_ms": int(time.time() * 1000),
        "count": len(leads),
        "leads": leads
    }

async def run_clean_markdown(target_url: str):
    parsed = httpx.URL(target_url)

    # Specialized Hacker News Reader (Bypasses HN 419)
    if "news.ycombinator.com" in parsed.host:
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get("https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30")
                if res.status_code == 200:
                    hits = res.json().get("hits", [])
                    md = "# Hacker News Front Page\n\n"
                    for idx, s in enumerate(hits):
                        u = s.get("url") or f"https://news.ycombinator.com/item?id={s.get('objectID')}"
                        md += f"### {idx + 1}. [{s.get('title')}]({u})\n"
                        md += f"* **Points:** {s.get('points', 0)} | **By:** {s.get('author')} | **Comments:** {s.get('num_comments', 0)}\n\n"
                    sanitized = sanitize_prompt(md)
                    return {
                        "status": "success",
                        "event_name": "clean-markdown-fetch",
                        "feed": "/v1/fuel/llm-clean-markdown",
                        "target_url": target_url,
                        "title": "Hacker News — Front Page",
                        "token_estimate": max(1, len(sanitized) // 4),
                        "sanitized": True,
                        "engine": "hn-algolia-reader",
                        "markdown": sanitized,
                        "timestamp_ms": int(time.time() * 1000)
                    }
        except Exception as e:
            Actor.log.warning(f"HN Algolia reader failed: {e}")

    # General Direct Fetch with Realistic Browser Headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }

    html = ""
    status_code = 200
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            res = await client.get(target_url, headers=headers)
            status_code = res.status_code
            if status_code == 404:
                return {"status": "error", "error": "upstream_target_unreachable", "http_status": 404, "target_url": target_url}
            if res.status_code == 200:
                html = res.text
    except Exception as e:
        Actor.log.warning(f"Direct fetch failed: {e}")

    # Jina Reader Fallback if blocked or empty
    if not html or status_code in (403, 419, 429, 503):
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                jina_res = await client.get(f"https://r.jina.ai/{target_url}", headers={"User-Agent": "Mozilla/5.0"})
                if jina_res.status_code == 404:
                    return {"status": "error", "error": "upstream_target_unreachable", "http_status": 404, "target_url": target_url}
                if jina_res.status_code == 200 and len(jina_res.text.strip()) > 20:
                    sanitized = sanitize_prompt(jina_res.text)
                    return {
                        "status": "success",
                        "event_name": "clean-markdown-fetch",
                        "feed": "/v1/fuel/llm-clean-markdown",
                        "target_url": target_url,
                        "title": parsed.host,
                        "token_estimate": max(1, len(sanitized) // 4),
                        "sanitized": True,
                        "engine": "jina-stealth-reader",
                        "markdown": sanitized[:100000],
                        "timestamp_ms": int(time.time() * 1000)
                    }
        except Exception as e:
            Actor.log.warning(f"Jina reader fallback failed: {e}")

    if not html:
        return {"status": "error", "error": "upstream_target_unreachable", "http_status": status_code or 502, "target_url": target_url}

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else parsed.host

    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "svg", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator="\n\n")
    cleaned_text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()
    if not cleaned_text:
        return {"status": "error", "error": "upstream_target_empty", "http_status": 422, "target_url": target_url}

    sanitized = sanitize_prompt(cleaned_text)

    return {
        "status": "success",
        "event_name": "clean-markdown-fetch",
        "feed": "/v1/fuel/llm-clean-markdown",
        "target_url": target_url,
        "title": title,
        "token_estimate": max(1, len(sanitized) // 4),
        "sanitized": True,
        "engine": "native-html-sanitizer",
        "markdown": sanitized[:100000],
        "timestamp_ms": int(time.time() * 1000)
    }

async def run_ecom_price(target_url: str):
    parsed = httpx.URL(target_url)

    # 1. Shopify direct JSON API
    if "/products/" in parsed.path:
        handle = parsed.path.split("/products/")[1].split("/")[0].split("?")[0]
        if handle:
            try:
                async with httpx.AsyncClient(timeout=6.0) as client:
                    json_url = f"{parsed.scheme}://{parsed.host}/products/{handle}.json"
                    res = await client.get(json_url, headers={"User-Agent": "Mozilla/5.0"})
                    if res.status_code == 200:
                        p = res.json().get("product", {})
                        variants = p.get("variants", [])
                        if variants:
                            v = variants[0]
                            price = float(v.get("price", 0.0))
                            compare = float(v.get("compare_at_price") or price)
                            return {
                                "status": "success",
                                "event_name": "ecom-product-check",
                                "feed": "/v1/fuel/ecom-price-stock",
                                "platform": "Shopify (Native API)",
                                "product_url": target_url,
                                "title": p.get("title", "Product"),
                                "price": price,
                                "compare_at_price": compare,
                                "discount_delta": round(max(0.0, compare - price), 2),
                                "currency": "USD",
                                "in_stock": v.get("available", True),
                                "sku": v.get("sku") or "N/A",
                                "timestamp_ms": int(time.time() * 1000)
                            }
            except: pass

    # 2. HTML Inspection (JSON-LD / OpenGraph / Price Selectors)
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            res = await client.get(target_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            if res.status_code >= 400:
                return {"status": "error", "error": "upstream_target_unreachable", "http_status": res.status_code, "product_url": target_url}
            html = res.text
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else "Product"
            price = None
            currency = "USD"
            platform = "OpenGraph / HTML"

            # Check JSON-LD Product offers
            import json
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "")
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        offers = item.get("offers")
                        offer = offers[0] if isinstance(offers, list) and offers else offers
                        if isinstance(offer, dict) and offer.get("price") is not None:
                            price = float(str(offer["price"]).replace(",", ""))
                            currency = str(offer.get("priceCurrency") or currency)
                            platform = "Schema.org JSON-LD"
                            break
                    if price is not None:
                        break
                except Exception:
                    pass

            # Check OpenGraph / itemprop / common price CSS classes
            if price is None:
                og_price = soup.find("meta", property=re.compile(r"price:amount", re.I)) or soup.find(attrs={"itemprop": "price"})
                raw_val = (og_price.get("content") or og_price.get_text()) if og_price else None
                if not raw_val:
                    price_el = soup.select_one(".price_color, [data-product-price], .product-price, .price")
                    raw_val = price_el.get_text() if price_el else None
                if raw_val:
                    m = re.search(r"([0-9]+(?:[.,][0-9]+)?)", raw_val.replace(",", ""))
                    if m:
                        price = float(m.group(1))
                    if "£" in raw_val:
                        currency = "GBP"
                    elif "€" in raw_val:
                        currency = "EUR"

            if price is None:
                return {"status": "error", "error": "product_price_not_found", "product_url": target_url, "title": title}

            return {
                "status": "success",
                "event_name": "ecom-product-check",
                "feed": "/v1/fuel/ecom-price-stock",
                "platform": platform,
                "product_url": target_url,
                "title": title,
                "price": price,
                "currency": currency,
                "in_stock": "out of stock" not in html.lower(),
                "discount_delta": 0.0,
                "sku": "HTML-VERIFIED",
                "timestamp_ms": int(time.time() * 1000)
            }
    except Exception as e:
        Actor.log.warning(f"Ecom fetch failed: {e}")

    return {"status": "error", "error": "upstream_target_unreachable", "product_url": target_url}

async def run_reverse_engineer(target_url: str):
    import json
    import urllib.parse
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    html = ""
    final_url = target_url
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            res = await client.get(target_url, headers=headers)
            if res.status_code == 200:
                html = res.text
                final_url = str(res.url)
    except Exception as e:
        Actor.log.warning(f"Direct fetch failed in REA: {e}")

    if not html:
        return {"status": "error", "error": "upstream_target_unreachable", "target_url": target_url}

    parsed_url = urllib.parse.urlparse(final_url)
    origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

    discovered_endpoints = []
    hydration_state = {}
    json_ld_schemas = []
    frameworks_detected = []

    # 1. Next.js __NEXT_DATA__
    next_match = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>({.*?})</script>', html, re.DOTALL | re.IGNORECASE)
    if next_match:
        frameworks_detected.append("Next.js")
        try:
            next_data = json.loads(next_match.group(1))
            build_id = next_data.get("buildId")
            page = next_data.get("page", "")
            hydration_state["next_js"] = {
                "page": page,
                "buildId": build_id,
                "query": next_data.get("query"),
                "props": next_data.get("props", {}).get("pageProps", {})
            }
            if build_id and page and not page.startswith("/404"):
                clean_path = page
                if clean_path == "/":
                    clean_path = "/index"
                discovered_endpoints.append({
                    "type": "Next.js Hydration Route",
                    "method": "GET",
                    "url": f"{origin}/_next/data/{build_id}{clean_path}.json",
                    "description": "Direct JSON endpoint delivering pre-rendered pageProps without HTML rendering"
                })
        except Exception:
            pass

    # 2. Nuxt.js / Vue
    nuxt_match = re.search(r'window\.__NUXT__\s*=\s*({.*?});?</script>', html, re.DOTALL | re.IGNORECASE)
    if nuxt_match:
        frameworks_detected.append("Nuxt.js")
        hydration_state["nuxt"] = {"detected": True, "raw_snippet": nuxt_match.group(1)[:200]}

    # 3. JSON-LD / schema.org
    json_ld_matches = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
    for j_str in json_ld_matches:
        try:
            j_obj = json.loads(j_str.strip())
            json_ld_schemas.append(j_obj)
        except Exception:
            pass
    if json_ld_schemas:
        frameworks_detected.append("Schema.org (JSON-LD)")

    # 4. Scan for API routes in script tags & inline JS
    api_patterns = [
        r'["\'](/api/v[0-9]/[^"\'\s<>]+)["\']',
        r'["\'](/api/[^"\'\s<>]+)["\']',
        r'["\'](/graphql[^"\'\s<>]*)["\']',
        r'["\'](https?://[^"\'\s<>]+/api/[^"\'\s<>]+)["\']'
    ]
    seen_urls = set()
    for pat in api_patterns:
        for m in re.findall(pat, html):
            if not any(ext in m.lower() for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ttf", ".webp"]):
                full_api = urllib.parse.urljoin(origin, m)
                if full_api not in seen_urls:
                    seen_urls.add(full_api)
                    discovered_endpoints.append({
                        "type": "Internal REST/GraphQL Route",
                        "method": "POST" if "graphql" in full_api else "GET",
                        "url": full_api,
                        "description": "Backend API endpoint extracted from client-side JavaScript bundle"
                    })

    # 5. OpenAPI 3.1.0 Specification Draft
    openapi_spec = {
        "openapi": "3.1.0",
        "info": {
            "title": f"Reverse-Engineered API: {parsed_url.netloc}",
            "version": "1.0.0",
            "description": f"Auto-generated by Kurox REA Engine for {target_url}"
        },
        "servers": [{"url": origin}],
        "paths": {}
    }
    for ep in discovered_endpoints[:10]:
        rel_path = ep["url"].replace(origin, "")
        if not rel_path.startswith("/"):
            rel_path = "/" + rel_path
        openapi_spec["paths"][rel_path] = {
            ep["method"].lower(): {
                "summary": ep.get("description"),
                "responses": {
                    "200": {
                        "description": "JSON Response payload",
                        "content": {"application/json": {"schema": {"type": "object"}}}
                    }
                }
            }
        }

    # 6. Zero-Scrape Bypass Scripts
    primary_url = discovered_endpoints[0]["url"] if discovered_endpoints else target_url
    is_json = bool(discovered_endpoints)
    accept_hdr = "application/json" if is_json else "text/html,application/xhtml+xml,application/xml"

    bypass_code = {
        "curl": f"curl -X GET '{primary_url}' \\\n  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)' \\\n  -H 'Accept: {accept_hdr}'",
        "python": f"""import httpx

url = '{primary_url}'
headers = {{
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '{accept_hdr}'
}}

with httpx.Client(timeout=10.0) as client:
    response = client.get(url, headers=headers)
    print(f"Status: {{response.status_code}}")
    try:
        data = response.json()
        print(data)
    except Exception:
        print(response.text[:500])
""",
        "typescript": f"""import fetch from 'node-fetch';

async function queryBypass() {{
  const res = await fetch('{primary_url}', {{
    headers: {{
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      'Accept': '{accept_hdr}'
    }}
  }});
  const data = await res.json();
  console.log(data);
}}

queryBypass();
"""
    }

    return {
        "status": "success",
        "event_name": "reverse-engineer-target",
        "engine": "Reverse Engineer Anything (REA) v1.0",
        "target_url": target_url,
        "origin": origin,
        "frameworks_detected": frameworks_detected or ["Standard Web / SSR"],
        "discovered_endpoints": discovered_endpoints[:15],
        "hydration_state": hydration_state,
        "json_ld_schemas": json_ld_schemas[:5],
        "openapi_spec": openapi_spec,
        "bypass_code": bypass_code,
        "timestamp_ms": int(time.time() * 1000)
    }

ACTOR_ID_TO_MODE = {
    "2KWgMEUJOiSzDpxeW": "llm-clean-markdown",       # kuroxreal/llm-clean-markdown-ppe
    "JoVOb6vKPFaNhDDcj": "ecom-price-stock",         # kuroxreal/ecom-price-stock-ppe
    "uOQ4jLOToRTwe10G1": "reverse-engineer-anything",# kuroxreal/reverse-engineer-anything
    "2AbJGn42avqlwZo5V": "b2b-intent-leads",         # kuroxreal/b2b-intent-leads-ppe
}


def _extract_max_leads(actor_input: dict) -> int:
    raw = actor_input.get("maxLeads")
    if raw is None:
        raw = actor_input.get("limit")
    if raw is None:
        return DEFAULT_B2B_LEADS
    try:
        return max(1, min(MAX_B2B_LEADS, int(raw)))
    except Exception:
        return DEFAULT_B2B_LEADS


def _parse_batch_urls(actor_input: dict) -> list:
    raw_urls = actor_input.get("urls")
    if not isinstance(raw_urls, list):
        return []
    cleaned = []
    seen = set()
    for entry in raw_urls:
        if not isinstance(entry, str):
            continue
        u = entry.strip()
        if not u.startswith(("http://", "https://")) or u in seen:
            continue
        seen.add(u)
        cleaned.append(u)
        if len(cleaned) >= MAX_BATCH_URLS:
            break
    return cleaned


async def _run_url_batch_mode(
    urls_to_run: list,
    is_batch_input: bool,
    worker_fn,
    event_name: str,
    valid_fn,
    unit_price_usd: float,
    error_code: str,
    url_field: str = "target_url",
):
    sem = asyncio.Semaphore(5)

    async def run_one(target: str):
        async with sem:
            try:
                return target, await worker_fn(target)
            except Exception as exc:
                return target, {"status": "error", "error": str(exc), url_field: target}

    pairs = await asyncio.gather(*(run_one(u) for u in urls_to_run))
    succeeded = []
    failed_urls = []
    for target, res in pairs:
        if isinstance(res, dict) and valid_fn(res):
            if "timestamp_ms" not in res:
                res["timestamp_ms"] = int(time.time() * 1000)
            succeeded.append(res)
        else:
            failed_urls.append(target)

    if not succeeded:
        Actor.log.error("All %d URL(s) failed for %s (Not charged)", len(urls_to_run), event_name)
        await Actor.set_status_message(f"Failed all {len(urls_to_run)} URL(s) — Buyer NOT charged.")
        payload = {"status": "error", "error": error_code, "charged": False, url_field: urls_to_run[0]}
        if is_batch_input:
            payload["failed_urls"] = failed_urls
        await Actor.push_data(payload)
        return

    charge_count = len(succeeded)
    Actor.log.info(
        "Batch %s completed: %d succeeded, %d skipped. Charging %d x %s ($%.3f USD)",
        event_name, charge_count, len(failed_urls), charge_count, event_name, charge_count * unit_price_usd,
    )
    await Actor.charge(event_name, count=charge_count)
    await Actor.set_status_message(
        f"Completed {charge_count}/{len(urls_to_run)} URLs (billed {charge_count} x {event_name})."
    )
    await Actor.push_data(succeeded if is_batch_input else succeeded[0])


async def main():
    async with Actor:
        actor_input = await Actor.get_input() or {}
        actor_id = os.environ.get("APIFY_ACTOR_ID", "")
        mode = ACTOR_ID_TO_MODE.get(actor_id) or actor_input.get("mode") or os.environ.get("ACTOR_MODE") or "b2b-intent-leads"
        raw_url = (actor_input.get("url") or actor_input.get("product_url") or actor_input.get("target_url") or "").strip()
        if "ecom" in mode.lower():
            pref = (actor_input.get("product_url") or "").strip()
            if pref:
                raw_url = pref
            elif not raw_url or raw_url.rstrip("/") == "https://news.ycombinator.com":
                raw_url = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
        elif not raw_url:
            if "markdown" in mode.lower() or "reverse" in mode.lower():
                raw_url = "https://example.com"
            else:
                raw_url = "https://news.ycombinator.com"
        target_url = raw_url
        batch_urls = _parse_batch_urls(actor_input)
        is_batch_urls = len(batch_urls) > 0
        urls_to_run = batch_urls if is_batch_urls else [target_url]
        max_leads = _extract_max_leads(actor_input)
        category = actor_input.get("category") or "all"

        Actor.log.info("AgentFuel402 Starting run in mode: %s (actor_id=%s)", mode, actor_id or "local")

        if "markdown" in mode.lower():
            await _run_url_batch_mode(
                urls_to_run=urls_to_run,
                is_batch_input=is_batch_urls,
                worker_fn=run_clean_markdown,
                event_name="clean-markdown-fetch",
                valid_fn=lambda r: r.get("status") == "success" and bool(r.get("markdown")),
                unit_price_usd=0.003,
                error_code="upstream_target_unreachable",
                url_field="target_url",
            )
            return

        if "ecom" in mode.lower() or "price" in mode.lower():
            await _run_url_batch_mode(
                urls_to_run=urls_to_run,
                is_batch_input=is_batch_urls,
                worker_fn=run_ecom_price,
                event_name="ecom-product-check",
                valid_fn=lambda r: r.get("status") == "success",
                unit_price_usd=0.003,
                error_code="upstream_target_unreachable",
                url_field="product_url",
            )
            return

        if "reverse" in mode.lower() or "rea" in mode.lower():
            await _run_url_batch_mode(
                urls_to_run=urls_to_run,
                is_batch_input=is_batch_urls,
                worker_fn=run_reverse_engineer,
                event_name="reverse-engineer-target",
                valid_fn=lambda r: r.get("status") == "success",
                unit_price_usd=0.015,
                error_code="reverse_engineering_failed",
                url_field="target_url",
            )
            return

        # Default: B2B Intent Leads Batch Engine (default 50, max 500; 1 PPE per delivered lead)
        event_name = "lead-signal-fetch"
        result = await run_b2b_leads(max_leads, category)
        delivered_leads = (result.get("leads") or [])[:max_leads] if result else []
        if not result or result.get("status") != "success" or not delivered_leads:
            Actor.log.error("Failed to fetch B2B leads (Not charged)")
            await Actor.set_status_message("B2B lead generation failed — Buyer NOT charged.")
            await Actor.push_data({"error": "lead_generation_failed", "charged": False})
            return

        charge_count = len(delivered_leads)
        Actor.log.info("B2B leads generated (%d leads). Charging %d x %s ($%.2f USD)", charge_count, charge_count, event_name, charge_count * 0.01)
        await Actor.charge(event_name, count=charge_count)
        ts = result.get("timestamp_ms") or int(time.time() * 1000)
        rows = [
            {
                "status": "success",
                "event_name": event_name,
                "feed": "/v1/fuel/b2b-intent-leads",
                "timestamp_ms": ts,
                "count": 1,
                **lead,
            }
            for lead in delivered_leads
        ]
        await Actor.push_data(rows)
        await Actor.set_status_message(f"Delivered {charge_count} B2B leads (billed {charge_count} x {event_name}).")
        Actor.log.info("Successfully pushed %d lead rows and settled %d x %s", len(rows), charge_count, event_name)

if __name__ == "__main__":
    asyncio.run(main())
