# @kurox_real/agentfuel402

> Zero-API-key **MCP Server & CLI** for **[AgentFuel402](https://agentfuel402.ak10082247.workers.dev)** — real-time B2B intent leads, clean LLM Markdown, e-commerce price/stock extraction, PyPI/npm SDK specs, and **Reverse Engineer Anything (REA)**.
> Pay per request via **x402 v2** on **Solana Mainnet USDC** (0 SOL gas) or **Base Mainnet USDC** (0 ETH gas) — or run in **Apify Store fiat/credit-card pay-per-event** mode with zero crypto setup.

---

## 5 Included Tools

| Tool / CLI Command | Price (x402 USDC) | Free Preview | Fiat / Credit Card Actor |
| :--- | :--- | :--- | :--- |
| `fuel_b2b_leads` / `leads` | `$0.010` | `GET /v1/preview/leads` | [b2b-intent-leads-ppe](https://apify.com/kuroxreal/b2b-intent-leads-ppe) |
| `fuel_clean_markdown` / `markdown` | `$0.005` | `GET /v1/preview/llm-clean-markdown` | [llm-clean-markdown-ppe](https://apify.com/kuroxreal/llm-clean-markdown-ppe) |
| `fuel_ecom_price_stock` / `ecom` | `$0.005` | `GET /v1/preview/ecom-price-stock` | [ecom-price-stock-ppe](https://apify.com/kuroxreal/ecom-price-stock-ppe) |
| `fuel_sdk_spec` / `sdk` | `$0.005` | `GET /v1/preview/sdk-live-spec` | — |
| `fuel_reverse_engineer` / `rea` | `$0.020` | Paid x402 / Apify only | [reverse-engineer-anything](https://apify.com/kuroxreal/reverse-engineer-anything) |

---

## Quick Start

### 1. CLI (Zero-Install `npx`)
```bash
# Live B2B intent leads preview (zero keys required)
npx -y @kurox_real/agentfuel402 leads --category ai --limit 5

# Clean any URL to prompt-injection-sanitized Markdown
npx -y @kurox_real/agentfuel402 markdown https://example.com

# Extract live Schema.org / Shopify price & stock
npx -y @kurox_real/agentfuel402 ecom https://scrapeme.live/shop/Bulbasaur/

# Check latest PyPI or npm package release
npx -y @kurox_real/agentfuel402 sdk viem --ecosystem npm

# Reverse-engineer hidden APIs + OpenAPI 3.1 (requires x402 key)
SOLANA_PRIVATE_KEY=... npx -y @kurox_real/agentfuel402 rea https://example.com
```

### 2. Claude Desktop / Cursor / Windsurf MCP (`stdio`)
```json
{
  "mcpServers": {
    "agentfuel402": {
      "command": "npx",
      "args": ["-y", "@kurox_real/agentfuel402"],
      "env": {
        "SOLANA_PRIVATE_KEY": "optional_base58_for_solana_usdc_autopay",
        "X402_PRIVATE_KEY": "optional_0x_hex_for_base_usdc_autopay"
      }
    }
  }
}
```

Or connect directly via remote Streamable HTTP MCP (no local install needed):
`https://agentfuel402.ak10082247.workers.dev/mcp`

---

## Billing Modes (Non-Custodial)
- **Free Preview**: Omit wallet keys to inspect live preview responses on `/v1/preview/*`.
- **Solana Mainnet USDC (`PayAI` fee-sponsored, 0 SOL gas)**: Set `SOLANA_PRIVATE_KEY` (Base58 or 64-byte JSON array).
- **Base Mainnet USDC (`CDP / PayAI` EIP-3009, 0 ETH gas)**: Set `X402_PRIVATE_KEY` (`0x...`).
- **Prefer credit card / no crypto wallet?** Use the published Apify Store Pay-Per-Event actors at https://apify.com/kuroxreal.

## License
MIT © kurox_real
