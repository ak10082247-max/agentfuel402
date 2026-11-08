# ⚡ AgentFuel402 — Consumable B2B, E-Commerce & Developer Data Factory

[![Edge Status](https://img.shields.io/badge/Cloudflare_Edge-0ms_Cold_Start-F38020?logo=cloudflare)](https://agentfuel402.ak10082247.workers.dev/health)
[![Protocol](https://img.shields.io/badge/x402_V2-Base_%26_Solana_USDC-0052FF)](https://agentfuel402.ak10082247.workers.dev/.well-known/x402.json)
[![Apify Store](https://img.shields.io/badge/Apify_Store-Pay--Per--Event-00A65A?logo=apify)](https://apify.com/kuroxreal)
[![MCP Protocol](https://img.shields.io/badge/MCP-JSON--RPC_2.0-8B5CF6)](https://agentfuel402.ak10082247.workers.dev/mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **High-frequency, non-cacheable consumable data feeds for autonomous AI agents, sales outreach automation (Clay, n8n, Make.com), e-commerce intelligence, and developer LLM workflows.**

AgentFuel402 delivers enterprise consumable data across 3 distinct distribution rails:
1. **Apify Store:** Micro-fiat Pay-Per-Event (PPE) with zero monthly fees.
2. **Cloudflare Edge x402:** Dual-chain machine-to-machine micropayments (Base & Solana USDC).
3. **Official MCP Registry:** Streamable HTTP Model Context Protocol tools for Claude Desktop, Cursor, and LangChain.

---

## 🛡️ "Verify -> Fetch -> Settle" Resilience Guarantee

AgentFuel402 guarantees that **buyers are never charged for dead links or upstream failures**:
1. When a paid request arrives, the cryptographic authorization or Pay-Per-Event token is **pre-verified** (`/verify`).
2. The target content engine executes live data extraction with multi-tier anti-bot fallbacks.
3. If an upstream target returns HTTP 404, empty content, or fails to respond, the engine immediately halts and returns `HTTP 422 Unprocessable Entity` with `charged: false`.
4. On-chain settlement (`/settle`) or PPE charging (`Actor.charge`) occurs **ONLY AFTER** valid, non-empty data is confirmed.

---

## 🚀 Live Endpoints & Pricing Matrix

| Feed Endpoint | Price Tier (x402 USDC) | Apify PPE Event | Primary Use Case |
| :--- | :---: | :---: | :--- |
| **`/v1/fuel/b2b-intent-leads`** | **`$0.010 USDC`** | **`$0.030 USD`** (`lead-signal-fetch`) | Aggregates early-stage tech company product launches, founder discussion threads, hiring alerts, and tech stacks with Intent Scores (30–100). |
| **`/v1/fuel/llm-clean-markdown`** | **`$0.005 USDC`** | **`$0.015 USD`** (`clean-markdown-fetch`) | Strips noisy JavaScript, ads, and navigation; normalizes HTML to clean Markdown; enforces SSRF protection and deterministic prompt-injection defense. |
| **`/v1/fuel/ecom-price-stock`** | **`$0.005 USDC`** | **`$0.015 USD`** (`ecom-product-check`) | Real-time price, currency, SKU variants, discount deltas, and in-stock inventory monitoring for Shopify & Schema.org products. |
| **`/v1/fuel/sdk-live-spec`** | **`$0.005 USDC`** | **`$0.010 USD`** (`sdk-spec-check`) | Verified PyPI & npm metadata, latest stable SemVer releases, deprecation notices, and breaking-change alerts for AI code generators. |
| **`/v1/fuel/reverse-engineer`** | **`$0.020 USDC`** | **`$0.050 USD`** (`reverse-engineer-target`) | **Reverse Engineer Anything (REA):** Deep reverse-engineering of target web platforms: extracts hidden internal REST/GraphQL endpoints, hydration state (`__NEXT_DATA__`, Redux, JSON-LD), auto-generates OpenAPI 3.1 spec and zero-scrape Python/cURL bypass code. |

---

## 🤖 Official MCP Registry Integration

AgentFuel402 is registered in the official Model Context Protocol Registry as **`io.github.ak10082247-max/agentfuel402`**.

### Cursor & Claude Desktop Config (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "agentfuel402": {
      "url": "https://agentfuel402.ak10082247.workers.dev/mcp",
      "transport": "http"
    }
  }
}
```

### Supported MCP Tools
- `fuel_b2b_leads`: `{ "limit": 10, "category": "all" }`
- `fuel_clean_markdown`: `{ "url": "https://news.ycombinator.com", "strip_images": false }`
- `fuel_ecom_price_stock`: `{ "url": "https://shop.allbirds.com/products/mens-tree-runners" }`
- `fuel_sdk_spec`: `{ "package": "fastapi", "ecosystem": "pypi" }`
- `fuel_reverse_engineer`: `{ "url": "https://sample-store.com/catalog" }`

---

## 🔍 Reverse Engineer Anything (REA) Engine

Inspired by developer reverse-engineering workflows (such as `morluto/rea`), the **AgentFuel402 REA Engine** provides cloud-hosted, zero-installation reverse engineering for arbitrary web applications:

1. **Hydration Unmasking:** Extracts `__NEXT_DATA__`, Nuxt state, Redux stores, and Schema.org JSON-LD before DOM rendering.
2. **Hidden API Discovery:** Unmasks unannounced internal `/api/v[0-9]/` and `/graphql` routes from frontend JavaScript bundles.
3. **OpenAPI 3.1.0 Synthesis:** Automatically generates formal OpenAPI specs with paths, parameters, and payload schemas.
4. **Zero-Scrape Client Code:** Produces instant copy-pasteable Python (`httpx`), TypeScript (`fetch`), and `cURL` code targeting the backend directly—bypassing anti-bot blocks and fragile HTML scraping.

---

## 🛠️ Multi-Chain Micropayment Rails (x402 V2)

All paid routes support HTTP `402 Payment Required` with gasless facilitators:
- **Base Mainnet (`eip155:8453`)**: Circle USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` via EIP-712 `TransferWithAuthorization` to Merchant `0x80E0Ae84679b7f11bE171DaADd492FBECf628cd6`.
- **Solana Mainnet (`solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp`)**: SPL USDC `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` to Merchant ATA `DD3A7jaXFeHcif9eYj6Vhomuxypat5Yxi8ow6wxz27yL` (sponsored by PayAI `feePayer`).

### 🎟️ Agency Pass Prepay ($5.00 USD)
Call `POST /v1/pass/prepay` with $5.00 USDC to activate an `X-Fuel-Session` session token valid for **1,000 cross-feed calls** with zero per-request transaction signing.

---

## 📦 Apify Pay-Per-Event (PPE) Store Actors

1. [**B2B Intent Leads (`kuroxreal/b2b-intent-leads-ppe`)**](https://apify.com/kuroxreal/b2b-intent-leads-ppe): High-frequency buying intent signals for Clay, n8n & AI SDRs.
2. [**LLM Clean Markdown (`kuroxreal/llm-clean-markdown-ppe`)**](https://apify.com/kuroxreal/llm-clean-markdown-ppe): Token-optimized, ad-free web content extractor with prompt injection defense.
3. [**E-Commerce Price & Stock (`kuroxreal/ecom-price-stock-ppe`)**](https://apify.com/kuroxreal/ecom-price-stock-ppe): Real-time Shopify & Schema.org price, variant, and stock monitor.
4. [**Pulse402 Oracle (`kuroxreal/pulse402-oracle`)**](https://apify.com/kuroxreal/pulse402-oracle): High-frequency Base DEX liquidity & Polymarket odds alpha.

---

## 📑 License
MIT License. Built for autonomous AI agents and modern data automation pipelines.
