# ⚡ AgentFuel402 — Consumable B2B, E-Commerce & Developer Data Factory

[![Edge Status](https://img.shields.io/badge/Cloudflare_Edge-0ms_Cold_Start-F38020?logo=cloudflare)](https://agentfuel402.ak10082247.workers.dev/health)
[![Protocol](https://img.shields.io/badge/x402_V2-Base_%26_Solana_USDC-0052FF)](https://agentfuel402.ak10082247.workers.dev/.well-known/x402.json)
[![Apify Store](https://img.shields.io/badge/Apify_Store-Pay--Per--Event-00A65A?logo=apify)](https://apify.com/kuroxreal)
[![MCP Protocol](https://img.shields.io/badge/MCP-JSON--RPC_2.0-8B5CF6)](https://agentfuel402.ak10082247.workers.dev/mcp)

High-frequency, non-cacheable consumable data feeds for autonomous AI agents, sales outreach pipelines, e-commerce dropshippers, and automated LLM code generators.

## 🚀 Live Endpoints

| Feed Endpoint | Price (x402) | Apify PPE Event | Description |
| :--- | :---: | :---: | :--- |
| **`/v1/fuel/b2b-intent-leads`** | `$0.010 USDC` | `$0.030 USD` (`lead-signal-fetch`) | Newly launched tech companies from Show HN, ProductHunt & GitHub trending with tech-stack tags & hiring intent. |
| **`/v1/fuel/llm-clean-markdown`** | `$0.005 USDC` | `$0.015 USD` (`clean-markdown-fetch`) | Stripped, noise-free Markdown with deterministic prompt-injection defense and SSRF isolation. |
| **`/v1/fuel/ecom-price-stock`** | `$0.005 USDC` | `$0.015 USD` (`ecom-product-check`) | Real-time prices, stock status, discount deltas, and SKU variants from Shopify & Schema.org. |
| **`/v1/fuel/sdk-live-spec`** | `$0.005 USDC` | `$0.010 USD` (`sdk-spec-check`) | Live PyPI & npm metadata to prevent hallucinated versions and detect breaking changes. |

---

## 🛠️ Multi-Chain Payment Rails (x402 V2)

All `/v1/fuel/*` endpoints enforce HTTP `402 Payment Required` supporting gasless settlement:
- **Base Mainnet (`eip155:8453`)**: Circle USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` via EIP-712 `TransferWithAuthorization` to `0x80E0Ae84679b7f11bE171DaADd492FBECf628cd6`.
- **Solana Mainnet (`solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp`)**: SPL USDC `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` to Merchant ATA `DD3A7jaXFeHcif9eYj6Vhomuxypat5Yxi8ow6wxz27yL` (sponsored by PayAI `feePayer`).

### 🎟️ Agency Pass Prepay ($5.00 USD)
Call `POST /v1/pass/prepay` with $5.00 USDC to receive an `X-Fuel-Session` token granting **1,000 cross-feed calls** with zero per-request gas or signature overhead.

---

## 🤖 Remote MCP Server

Connect any Model Context Protocol client (Claude Desktop, Cursor, n8n, LangChain) directly:

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

*Note: Free trial includes 3 free tool calls per IP.*

---

## 📦 Apify Store Pay-Per-Event (PPE) Actors

1. `kuroxreal/b2b-intent-leads-ppe` ($0.030 USD / lead-signal-fetch)
2. `kuroxreal/llm-clean-markdown-ppe` ($0.015 USD / clean-markdown-fetch)
3. `kuroxreal/ecom-price-stock-ppe` ($0.015 USD / ecom-product-check)

---

## 📑 License
MIT
