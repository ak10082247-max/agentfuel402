#!/usr/bin/env node
/**
 * @kurox_real/agentfuel402 (v1.0.0)
 * -----------------------------------
 * Official MCP Server & CLI for AgentFuel402 (https://agentfuel402.ak10082247.workers.dev)
 * Supports dual-chain x402 v2 auto-payment (Solana USDC via PayAI & Base USDC via EIP-3009),
 * free /v1/preview/* evaluation, and honest Apify Store credit-card PPE upsell links.
 */
import * as readline from "node:readline";
import {
  createGuardPayingFetchAsync,
  resolvePrivateKey,
  resolveSolanaPrivateKeyBytes,
  resolveSolanaRpcUrl,
} from "@kurox_real/solana-agent-kit-guard";

export const SERVICE_VERSION = "1.0.0";
export const AGENTFUEL_DEFAULT_URL =
  process.env.AGENTFUEL_URL || "https://agentfuel402.ak10082247.workers.dev";
export const APIFY_STORE_URL = "https://apify.com/kuroxreal";

export const AGENTFUEL_UPGRADE_HINT =
  "Evaluated via free preview. Set SOLANA_PRIVATE_KEY (Solana USDC, 0 SOL gas) or X402_PRIVATE_KEY (Base USDC, 0 ETH gas) for paid /v1/fuel/* endpoints ($0.005-$0.020 USDC), or use credit-card billing on Apify: https://apify.com/kuroxreal";

export const MCP_TOOLS = [
  {
    name: "fuel_b2b_leads",
    description:
      "Fetches live B2B buying intent signals, recent tech launches from Show HN, detected stacks, domains, and hiring flags. Cost: $0.010 USDC via x402 (free preview available).",
    inputSchema: {
      type: "object",
      properties: {
        category: {
          type: "string",
          description: "Filter category: all, ai, devtools, saas, fin, ecommerce",
          default: "all",
        },
        limit: {
          type: "integer",
          description: "Maximum lead signals to return (1-25)",
          default: 10,
        },
      },
    },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
  },
  {
    name: "fuel_clean_markdown",
    description:
      "Fetches any public URL, strips HTML noise, sanitizes prompt-injection attempts, and returns clean LLM Markdown with token counts. Cost: $0.005 USDC via x402.",
    inputSchema: {
      type: "object",
      properties: {
        url: {
          type: "string",
          description: "Public URL to fetch, clean, and convert to LLM Markdown",
          format: "uri",
        },
        strip_images: {
          type: "boolean",
          description: "Whether to strip image markdown tags",
          default: false,
        },
      },
      required: ["url"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
  },
  {
    name: "fuel_ecom_price_stock",
    description:
      "Extracts live price, currency, in-stock boolean, and SKU variants from any Shopify, WooCommerce, or Schema.org product URL. Cost: $0.005 USDC via x402.",
    inputSchema: {
      type: "object",
      properties: {
        url: {
          type: "string",
          description: "Shopify / WooCommerce / Schema.org product URL",
          format: "uri",
        },
      },
      required: ["url"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
  },
  {
    name: "fuel_sdk_spec",
    description:
      "Queries live PyPI and npm registries for latest stable package versions, release timestamps, and breaking-change signals. Cost: $0.005 USDC via x402.",
    inputSchema: {
      type: "object",
      properties: {
        package: {
          type: "string",
          description: "Package name on PyPI or npm (e.g. fastapi, viem, langchain)",
        },
        ecosystem: {
          type: "string",
          enum: ["pypi", "npm"],
          default: "pypi",
        },
      },
      required: ["package"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
  },
  {
    name: "fuel_reverse_engineer",
    description:
      "Extracts hidden internal REST/GraphQL endpoints and hydration state (__NEXT_DATA__, JSON-LD) and synthesizes OpenAPI 3.1 + curl/Python snippets. Cost: $0.020 USDC via x402.",
    inputSchema: {
      type: "object",
      properties: {
        url: {
          type: "string",
          description: "Target webpage or web platform URL to reverse-engineer",
        },
      },
      required: ["url"],
    },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
  },
];

interface RouteSpec {
  paidPath: string;
  previewPath?: string;
  previewMethod?: "GET" | "POST";
  apifyUrl: string;
  validate: (args: Record<string, any>) => string | null;
  buildPaidBody: (args: Record<string, any>) => Record<string, any>;
  buildPreviewQuery?: (args: Record<string, any>) => URLSearchParams;
  buildPreviewBody?: (args: Record<string, any>) => Record<string, any>;
}

const ROUTE_SPECS: Record<string, RouteSpec> = {
  fuel_b2b_leads: {
    paidPath: "/v1/fuel/b2b-intent-leads",
    previewPath: "/v1/preview/leads",
    previewMethod: "GET",
    apifyUrl: "https://apify.com/kuroxreal/b2b-intent-leads-ppe",
    validate: () => null,
    buildPaidBody: (a) => ({
      category: String(a.category || "all"),
      limit: Number.isFinite(Number(a.limit)) ? Number(a.limit) : 10,
    }),
    buildPreviewQuery: (a) =>
      new URLSearchParams({
        category: String(a.category || "all"),
        limit: String(Number.isFinite(Number(a.limit)) ? Number(a.limit) : 5),
      }),
  },
  fuel_clean_markdown: {
    paidPath: "/v1/fuel/llm-clean-markdown",
    previewPath: "/v1/preview/llm-clean-markdown",
    previewMethod: "GET",
    apifyUrl: "https://apify.com/kuroxreal/llm-clean-markdown-ppe",
    validate: (a) => (!a.url || typeof a.url !== "string" ? "url is required" : null),
    buildPaidBody: (a) => ({ url: a.url, strip_images: Boolean(a.strip_images) }),
    buildPreviewQuery: (a) => new URLSearchParams({ url: String(a.url) }),
  },
  fuel_ecom_price_stock: {
    paidPath: "/v1/fuel/ecom-price-stock",
    previewPath: "/v1/preview/ecom-price-stock",
    previewMethod: "GET",
    apifyUrl: "https://apify.com/kuroxreal/ecom-price-stock-ppe",
    validate: (a) => (!a.url || typeof a.url !== "string" ? "url is required" : null),
    buildPaidBody: (a) => ({ url: a.url }),
    buildPreviewQuery: (a) => new URLSearchParams({ url: String(a.url) }),
  },
  fuel_sdk_spec: {
    paidPath: "/v1/fuel/sdk-live-spec",
    previewPath: "/v1/preview/sdk-live-spec",
    previewMethod: "GET",
    apifyUrl: APIFY_STORE_URL,
    validate: (a) => (!a.package || typeof a.package !== "string" ? "package is required" : null),
    buildPaidBody: (a) => ({ package: a.package, ecosystem: a.ecosystem || "pypi" }),
    buildPreviewQuery: (a) =>
      new URLSearchParams({
        package: String(a.package),
        ecosystem: String(a.ecosystem || "pypi"),
      }),
  },
  fuel_reverse_engineer: {
    paidPath: "/v1/fuel/reverse-engineer",
    apifyUrl: "https://apify.com/kuroxreal/reverse-engineer-anything",
    validate: (a) => (!a.url || typeof a.url !== "string" ? "url is required" : null),
    buildPaidBody: (a) => ({ url: a.url }),
  },
};

export interface AgentFuelOptions {
  baseUrl?: string;
  privateKey?: string;
  solanaPrivateKey?: string | Uint8Array | number[];
  solanaRpcUrl?: string;
  paymentHeader?: string;
  customFetch?: typeof fetch;
}

export async function executeAgentFuelTool(
  toolName: string,
  args: Record<string, any> = {},
  options: AgentFuelOptions = {},
) {
  const spec = ROUTE_SPECS[toolName];
  if (!spec) {
    return { unknownTool: toolName };
  }

  const validationError = spec.validate(args);
  if (validationError) {
    return { validationError };
  }

  const baseUrl = (options.baseUrl || AGENTFUEL_DEFAULT_URL).replace(/\/$/, "");
  const baseFetch = options.customFetch ?? fetch;
  const evmPrivateKey = resolvePrivateKey({ x402PrivateKey: options.privateKey }, [
    "AGENTFUEL_PRIVATE_KEY",
  ]);
  const solanaSecretKeyBytes = resolveSolanaPrivateKeyBytes(
    { solanaPrivateKey: options.solanaPrivateKey },
    ["AGENTFUEL_SOLANA_PRIVATE_KEY"],
  );
  const solanaRpcUrl = resolveSolanaRpcUrl({ solanaRpcUrl: options.solanaRpcUrl });
  const paymentHeader =
    options.paymentHeader ??
    process.env.AGENTFUEL_PAYMENT_HEADER ??
    process.env.X402_PAYMENT_HEADER;

  const hasAutoPay = Boolean(evmPrivateKey || solanaSecretKeyBytes);
  const isPaid = Boolean(hasAutoPay || paymentHeader);
  const usePreview = !isPaid && Boolean(spec.previewPath);

  const caller = hasAutoPay
    ? await createGuardPayingFetchAsync({ evmPrivateKey, solanaSecretKeyBytes, solanaRpcUrl }, baseFetch)
    : baseFetch;

  let targetUrl = `${baseUrl}${usePreview ? spec.previewPath! : spec.paidPath}`;
  let method: "GET" | "POST" = "POST";
  let body: string | undefined;

  if (usePreview) {
    method = spec.previewMethod || "GET";
    if (method === "GET" && spec.buildPreviewQuery) {
      const qs = spec.buildPreviewQuery(args).toString();
      if (qs) targetUrl = `${targetUrl}?${qs}`;
    } else {
      body = JSON.stringify((spec.buildPreviewBody ?? spec.buildPaidBody)(args));
    }
  } else {
    body = JSON.stringify(spec.buildPaidBody(args));
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body) headers["Content-Type"] = "application/json";
  if (paymentHeader && !hasAutoPay && !usePreview) {
    headers["PAYMENT-SIGNATURE"] = paymentHeader;
  }

  const res = await caller(targetUrl, {
    method,
    headers,
    body,
    signal: AbortSignal.timeout(20000),
  });

  const paymentRequiredHeader = res.headers.get("PAYMENT-REQUIRED");
  const paymentResponseHeader = res.headers.get("PAYMENT-RESPONSE");
  const text = await res.text();
  let parsed: any;
  try {
    parsed = text ? JSON.parse(text) : {};
  } catch {
    parsed = { raw: text };
  }

  if (!res.ok) {
    return {
      isError: true,
      payload: {
        error: res.status === 402 ? "PAYMENT_REQUIRED_402" : `UPSTREAM_HTTP_${res.status}`,
        status: res.status,
        details: parsed,
        payment_required_header: paymentRequiredHeader || null,
        apify_fiat_actor: spec.apifyUrl,
        setup_hint:
          res.status === 402
            ? `Payment required. Set SOLANA_PRIVATE_KEY or X402_PRIVATE_KEY to pay automatically via x402, or use credit-card billing on Apify: ${spec.apifyUrl}`
            : undefined,
      },
    };
  }

  return {
    isError: false,
    payload: {
      ...(typeof parsed === "object" && parsed !== null ? parsed : { data: parsed }),
      x402_payment_mode: usePreview ? "free_preview" : hasAutoPay ? "x402_paid" : "x402_header",
      ...(paymentResponseHeader ? { payment_response: paymentResponseHeader } : {}),
      ...(usePreview ? { x402_upgrade_hint: AGENTFUEL_UPGRADE_HINT, apify_fiat_actor: spec.apifyUrl } : {}),
    },
  };
}

async function handleJsonRpc(line: string) {
  let req: any;
  try {
    req = JSON.parse(line);
  } catch {
    return;
  }
  const { id, method, params } = req;
  if (!method) return;

  if (method === "initialize") {
    process.stdout.write(
      JSON.stringify({
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: "2024-11-05",
          capabilities: { tools: { listChanged: false } },
          serverInfo: { name: "@kurox_real/agentfuel402", version: SERVICE_VERSION },
        },
      }) + "\n",
    );
    return;
  }

  if (method === "notifications/initialized") return;

  if (method === "ping") {
    process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result: {} }) + "\n");
    return;
  }

  if (method === "tools/list") {
    process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result: { tools: MCP_TOOLS } }) + "\n");
    return;
  }

  if (method === "tools/call") {
    const outcome = await executeAgentFuelTool(String(params?.name || ""), params?.arguments || {});
    if ("validationError" in outcome) {
      process.stdout.write(
        JSON.stringify({ jsonrpc: "2.0", id, error: { code: -32602, message: outcome.validationError } }) + "\n",
      );
      return;
    }
    if ("unknownTool" in outcome) {
      process.stdout.write(
        JSON.stringify({ jsonrpc: "2.0", id, error: { code: -32601, message: `Unknown tool: ${outcome.unknownTool}` } }) + "\n",
      );
      return;
    }
    process.stdout.write(
      JSON.stringify({
        jsonrpc: "2.0",
        id,
        result: {
          ...(outcome.isError ? { isError: true } : {}),
          content: [{ type: "text", text: JSON.stringify(outcome.payload) }],
        },
      }) + "\n",
    );
    return;
  }

  process.stdout.write(
    JSON.stringify({ jsonrpc: "2.0", id, error: { code: -32601, message: `Method not found: ${method}` } }) + "\n",
  );
}

function getFlag(args: string[], flag: string): string | undefined {
  const idx = args.indexOf(flag);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : undefined;
}

function printHelp() {
  console.log(`
@kurox_real/agentfuel402 (v${SERVICE_VERSION})
AgentFuel402 — Live Data, Markdown, E-Commerce & Reverse Engineering MCP + CLI

Usage:
  npx @kurox_real/agentfuel402 leads [--category ai] [--limit 5]
  npx @kurox_real/agentfuel402 markdown <URL> [--strip-images]
  npx @kurox_real/agentfuel402 ecom <PRODUCT_URL>
  npx @kurox_real/agentfuel402 sdk <PACKAGE> [--ecosystem npm|pypi]
  npx @kurox_real/agentfuel402 rea <URL>
  npx @kurox_real/agentfuel402                   Start MCP JSON-RPC 2.0 server on stdio

Paid x402 Auto-Signing (Dual-Chain Gasless):
  export SOLANA_PRIVATE_KEY=<base58>   # Solana USDC via PayAI (@x402/svm, 0 SOL gas)
  export X402_PRIVATE_KEY=0x...        # Base USDC via EIP-3009 (@x402/evm, 0 ETH gas)
  Remote MCP: https://agentfuel402.ak10082247.workers.dev/mcp
  Credit Card / Fiat Actors: https://apify.com/kuroxreal
`);
}

async function runCliCommand(cmd: string, args: string[]) {
  const positional = args.filter((a, i) => !a.startsWith("-") && args[i - 1] !== "--category" && args[i - 1] !== "--limit" && args[i - 1] !== "--ecosystem");
  const target = positional[1];

  const map: Record<string, { tool: string; params: Record<string, any> }> = {
    leads: {
      tool: "fuel_b2b_leads",
      params: { category: getFlag(args, "--category") || "all", limit: Number(getFlag(args, "--limit") || 5) },
    },
    markdown: {
      tool: "fuel_clean_markdown",
      params: { url: target, strip_images: args.includes("--strip-images") },
    },
    ecom: {
      tool: "fuel_ecom_price_stock",
      params: { url: target },
    },
    sdk: {
      tool: "fuel_sdk_spec",
      params: { package: target, ecosystem: getFlag(args, "--ecosystem") || "pypi" },
    },
    rea: {
      tool: "fuel_reverse_engineer",
      params: { url: target },
    },
  };

  const entry = map[cmd];
  if (!entry) return false;

  const outcome = await executeAgentFuelTool(entry.tool, entry.params);
  if ("validationError" in outcome || "unknownTool" in outcome) {
    console.error(JSON.stringify(outcome, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify(outcome.payload, null, 2));
  if (outcome.isError) process.exit(1);
  return true;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.includes("-h") || args.includes("--help") || args[0] === "help") {
    printHelp();
    process.exit(0);
  }

  if (args[0] && (await runCliCommand(args[0], args))) {
    return;
  }

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: false });
  rl.on("line", (line) => {
    void handleJsonRpc(line);
  });
}

const isMainEntry =
  typeof process !== "undefined" &&
  Array.isArray(process.argv) &&
  process.argv[1] &&
  /index\.(js|ts)$/.test(process.argv[1].replace(/\\/g, "/"));

if (isMainEntry) {
  main().catch((err) => {
    console.error("Fatal AgentFuel402 error:", err);
    process.exit(1);
  });
}
