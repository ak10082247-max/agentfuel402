/**
 * AgentFuel402 High-AOV Intelligence Store Engine (/store)
 * Serves pre-compiled daily datasets (Base/Solana Alpha, 500 B2B Startup Leads)
 * and live on-demand Security Audit Certificates & signed README badges.
 */

import {
  BASE_ALPHA_SNAPSHOT as baseAlphaSnapshot,
  B2B_LEADS_SNAPSHOT as b2bLeadsSnapshot,
} from "./data/store_snapshots.js";

const enc = new TextEncoder();

export const STORE_PRODUCTS = {
  "base-alpha-feed": {
    id: "base-alpha-feed",
    sku: "store-base-alpha-feed-v1",
    name: "Base & Solana Fresh Launch Alpha Feed",
    tagline:
      "Daily-compiled JSON/CSV drop of fresh Base Mainnet & Solana token pools with verified DEX liquidity ($10k+ tagged), GoPlus/RugCheck deployer risk checks & social links.",
    amountCents: 2900,
    amountMicro: 29000000,
    priceDisplay: "$29.00 USD / USDC",
    cadence: "Updated every 24h via automated GitHub Actions pipeline (+30d API Key)",
    formats: ["json", "csv"],
    defaultFormat: "json",
    filenameJson: "AgentFuel402_Base_Solana_Alpha_Feed.json",
    filenameCsv: "AgentFuel402_Base_Solana_Alpha_Feed.csv",
    bonusApiTtlSeconds: 30 * 24 * 60 * 60,
    tier: "store_alpha_30d",
    requiresTarget: false,
  },
  "b2b-startup-leads-500": {
    id: "b2b-startup-leads-500",
    sku: "store-b2b-startup-leads-500-v1",
    name: "Fresh AI & SaaS Startup Intent Leads Drop (Up to 500)",
    tagline:
      "Curated JSON/CSV drop of up to 500 newly launched AI/SaaS startups, HN Show/Hiring threads, Remotive hirers & fresh GitHub AI/MCP repos with stack tags and published contacts.",
    amountCents: 3900,
    amountMicro: 39000000,
    priceDisplay: "$39.00 USD / USDC",
    cadence: "Updated every 24h via automated GitHub Actions pipeline (+30d API Key)",
    formats: ["json", "csv"],
    defaultFormat: "csv",
    filenameJson: "AgentFuel402_B2B_Startup_Leads_500.json",
    filenameCsv: "AgentFuel402_B2B_Startup_Leads_500.csv",
    bonusApiTtlSeconds: 30 * 24 * 60 * 60,
    tier: "store_leads_30d",
    requiresTarget: false,
  },
  "instant-security-audit": {
    id: "instant-security-audit",
    sku: "store-instant-security-audit-v1",
    name: "Instant Smart Contract / MCP / Repo Security Audit Certificate",
    tagline:
      "Submit any public GitHub repo, Base Mainnet contract (0x...), or Solana mint to run live on-chain + static security checks and issue a signed JSON, Printable PDF Certificate & README SVG Badge.",
    amountCents: 999,
    amountMicro: 9990000,
    priceDisplay: "$9.99 USD / USDC",
    cadence: "On-demand real-time verification + 7-day downloadable receipt & badge",
    formats: ["json", "html", "svg"],
    defaultFormat: "json",
    filenameJson: "Kurox_Security_Audit_Certificate.json",
    filenameHtml: "Kurox_Security_Audit_Certificate.html",
    bonusApiTtlSeconds: 7 * 24 * 60 * 60,
    tier: "store_audit",
    requiresTarget: true,
  },
};

export function resolveStoreProduct(rawIdOrSku) {
  const key = String(rawIdOrSku || "").trim().toLowerCase();
  if (!key) return null;
  if (STORE_PRODUCTS[key]) return STORE_PRODUCTS[key];
  return Object.values(STORE_PRODUCTS).find((p) => p.sku.toLowerCase() === key) || null;
}

export function escStoreHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function csvCell(value) {
  const str = String(value ?? "");
  return /[",\r\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
}

function cleanSecret(value) {
  return typeof value === "string" ? value.replace(/[\uFEFF\x00-\x20\x7F]+/g, "") : "";
}

async function hmacSha256Hex(message, secret) {
  const normalized = cleanSecret(secret);
  if (normalized.length < 16) return null;
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(normalized),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeHexEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length || !a) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

const RAW_DATASET_URLS = {
  "base-alpha-feed": "https://raw.githubusercontent.com/ak10082247-max/agentfuel402/main/data/latest_base_alpha.json",
  "b2b-startup-leads-500": "https://raw.githubusercontent.com/ak10082247-max/agentfuel402/main/data/latest_b2b_leads.json",
};

export async function getStoreDataset(productId, env = {}, forceRefresh = false) {
  const fallback =
    productId === "base-alpha-feed"
      ? baseAlphaSnapshot
      : productId === "b2b-startup-leads-500"
        ? b2bLeadsSnapshot
        : null;
  if (!fallback) return null;

  const allowLiveRaw = forceRefresh || cleanSecret(env?.ENABLE_RAW_STORE_REFRESH) === "true";
  const rawUrl = RAW_DATASET_URLS[productId];
  if (!allowLiveRaw || !rawUrl) {
    return fallback;
  }

  try {
    const res = await fetch(rawUrl, {
      headers: { "User-Agent": "AgentFuel402-StoreLoader/1.0", Accept: "application/json" },
      cf: { cacheTtl: 300, cacheEverything: true },
      signal: AbortSignal.timeout(2500),
    });
    if (res.ok) {
      const liveData = await res.json();
      if (liveData && (Array.isArray(liveData.tokens) || Array.isArray(liveData.leads))) {
        return liveData;
      }
    }
  } catch {
    // Graceful fallback to compiled bundled snapshot
  }
  return fallback;
}

export function baseAlphaToCsv(dataset) {
  const headers = [
    "chain",
    "symbol",
    "token_address",
    "pool_address",
    "dex",
    "price_usd",
    "reserve_usd",
    "liquidity_over_10k",
    "fdv_usd",
    "volume_24h_usd",
    "txns_24h_buys",
    "txns_24h_sells",
    "deployer_dump_risk",
    "anomaly_flags",
    "website",
    "social_links",
    "security_provider",
    "pool_created_at",
  ];
  const rows = [headers.join(",")];
  for (const t of dataset?.tokens || []) {
    rows.push(
      [
        t.chain,
        t.symbol,
        t.token_address,
        t.pool_address,
        t.dex,
        t.price_usd,
        t.reserve_usd,
        t.liquidity_over_10k,
        t.fdv_usd,
        t.volume_24h_usd,
        t.txns_24h_buys,
        t.txns_24h_sells,
        t.deployer_dump_risk,
        Array.isArray(t.anomaly_flags) ? t.anomaly_flags.join(" | ") : "",
        t.website || "",
        Array.isArray(t.social_links) ? t.social_links.join(" | ") : "",
        t.security?.provider || "",
        t.pool_created_at || "",
      ]
        .map(csvCell)
        .join(","),
    );
  }
  return rows.join("\r\n") + "\r\n";
}

export function b2bLeadsToCsv(dataset) {
  const headers = [
    "company_name",
    "launch_headline",
    "domain",
    "website_url",
    "source_type",
    "source_url",
    "founder_or_contact",
    "email",
    "tech_stack",
    "hiring_intent",
    "intent_score",
    "published_at",
  ];
  const rows = [headers.join(",")];
  for (const lead of dataset?.leads || []) {
    rows.push(
      [
        lead.company_name,
        lead.launch_headline,
        lead.domain,
        lead.website_url,
        lead.source_type,
        lead.source_url,
        lead.founder_or_contact || "",
        lead.email || "",
        Array.isArray(lead.tech_stack) ? lead.tech_stack.join(" | ") : "",
        lead.hiring_intent,
        lead.intent_score,
        lead.published_at || "",
      ]
        .map(csvCell)
        .join(","),
    );
  }
  return rows.join("\r\n") + "\r\n";
}

export function getStoreSnapshotStats() {
  return {
    base_alpha: {
      compiled_at: baseAlphaSnapshot.compiled_at,
      total_tokens: baseAlphaSnapshot.total_tokens || (baseAlphaSnapshot.tokens || []).length,
      base_count: baseAlphaSnapshot.base_count || 0,
      solana_count: baseAlphaSnapshot.solana_count || 0,
      over_10k_liquidity_count: baseAlphaSnapshot.over_10k_liquidity_count || 0,
    },
    b2b_leads: {
      compiled_at: b2bLeadsSnapshot.compiled_at,
      total_leads: b2bLeadsSnapshot.total_leads || (b2bLeadsSnapshot.leads || []).length,
      verified_email_count: b2bLeadsSnapshot.verified_email_count || 0,
      hiring_count: b2bLeadsSnapshot.hiring_count || 0,
    },
  };
}

export function buildStoreCatalogResponse(origin) {
  const stats = getStoreSnapshotStats();
  const products = Object.values(STORE_PRODUCTS).map((p) => {
    const productStats =
      p.id === "base-alpha-feed"
        ? stats.base_alpha
        : p.id === "b2b-startup-leads-500"
          ? stats.b2b_leads
          : { on_demand_live: true, targets_supported: ["github_repo", "evm_contract", "solana_mint"] };
    return {
      id: p.id,
      sku: p.sku,
      name: p.name,
      tagline: p.tagline,
      price_usd: (p.amountCents / 100).toFixed(2),
      amount_cents: p.amountCents,
      amount_micro_usdc: String(p.amountMicro),
      formats: p.formats,
      cadence: p.cadence,
      requires_target: p.requiresTarget,
      live_stats: productStats,
      stripe_checkout_url: `${origin}/v1/store/checkout?sku=${encodeURIComponent(p.id)}`,
      x402_purchase_url: `${origin}/v1/store/buy?sku=${encodeURIComponent(p.id)}`,
    };
  });

  return {
    service: "agentfuel402-store",
    currency_rails: ["USD (Stripe Checkout)", "USDC on Base (eip155:8453)", "USDC on Solana (solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp)"],
    storefront_url: `${origin}/store`,
    download_endpoint: `${origin}/v1/store/download?token=...`,
    products,
  };
}

// ---------------------------------------------------------------------------
// PRODUCT C: INSTANT SECURITY AUDIT ENGINE (GitHub Repo / EVM / Solana)
// ---------------------------------------------------------------------------
export function validateAuditTarget(rawTarget) {
  const cleaned = String(rawTarget || "").trim();
  if (!cleaned) {
    return { valid: false, error: "Missing 'target' (GitHub owner/repo or URL, 0x EVM address, or Solana mint)." };
  }

  if (/^0x[a-fA-F0-9]{40}$/.test(cleaned)) {
    return { valid: true, kind: "evm_contract", target: cleaned, normalized: cleaned.toLowerCase() };
  }

  if (/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(cleaned)) {
    return { valid: true, kind: "solana_mint", target: cleaned, normalized: cleaned };
  }

  let repoSlug = cleaned;
  if (/^https?:\/\//i.test(cleaned)) {
    let parsed;
    try {
      parsed = new URL(cleaned);
    } catch {
      return { valid: false, error: "Malformed target URL." };
    }
    const host = parsed.hostname.toLowerCase().replace(/^www\./, "");
    if (host !== "github.com") {
      return { valid: false, error: "URL target must point to https://github.com/<owner>/<repo>." };
    }
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts.length < 2) {
      return { valid: false, error: "GitHub URL must include both <owner>/<repo>." };
    }
    repoSlug = `${parts[0]}/${parts[1].replace(/\.git$/i, "")}`;
  }

  if (/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repoSlug)) {
    const cleanSlug = repoSlug.replace(/\.git$/i, "");
    return { valid: true, kind: "github_repo", target: cleanSlug, normalized: cleanSlug };
  }

  return {
    valid: false,
    error: "Unsupported audit target. Provide a public GitHub repo (owner/repo), 0x EVM address, or Solana mint address.",
  };
}

async function auditGitHubRepository(repoSlug) {
  const ghHeaders = { "User-Agent": "Kurox-SecurityAudit/1.0", Accept: "application/vnd.github.v3+json" };
  const repoRes = await fetch(`https://api.github.com/repos/${repoSlug}`, {
    headers: ghHeaders,
    signal: AbortSignal.timeout(8000),
  });
  if (repoRes.status === 404) {
    const err = new Error(`GitHub repository '${repoSlug}' not found (HTTP 404).`);
    err.httpStatus = 404;
    throw err;
  }
  if (!repoRes.ok) {
    const err = new Error(`GitHub API error HTTP ${repoRes.status} while inspecting '${repoSlug}'.`);
    err.httpStatus = 502;
    throw err;
  }
  const repoMeta = await repoRes.json();

  let rootItems = [];
  try {
    const contentsRes = await fetch(`https://api.github.com/repos/${repoSlug}/contents`, {
      headers: ghHeaders,
      signal: AbortSignal.timeout(6000),
    });
    if (contentsRes.ok) {
      const parsed = await contentsRes.json();
      if (Array.isArray(parsed)) rootItems = parsed;
    }
  } catch {
    rootItems = [];
  }

  const fileNames = new Set(rootItems.map((i) => String(i.name || "").toLowerCase()));
  const findings = [];
  let score = 100;

  if (repoMeta.archived) {
    score -= 15;
    findings.push({ severity: "MEDIUM", check: "repo_maintenance", message: "Repository is archived (no active security patches)." });
  }
  if (!repoMeta.license?.spdx_id && !fileNames.has("license") && !fileNames.has("license.md")) {
    score -= 8;
    findings.push({ severity: "LOW", check: "license_presence", message: "No open-source LICENSE detected at repository root." });
  }
  if (!fileNames.has("security.md")) {
    score -= 10;
    findings.push({ severity: "LOW", check: "security_policy", message: "Missing SECURITY.md vulnerability disclosure policy." });
  }
  const leakedEnvFiles = [...fileNames].filter((f) => f === ".env" || f === ".env.production" || f.endsWith(".pem") || f.endsWith(".key"));
  if (leakedEnvFiles.length > 0) {
    score -= 35;
    findings.push({ severity: "CRITICAL", check: "committed_secrets_files", message: `Sensitive env/key files at root: ${leakedEnvFiles.join(", ")}` });
  }

  // Inspect package.json if present (unpinned deps / risky install hooks)
  if (fileNames.has("package.json")) {
    try {
      const pkgRes = await fetch(
        `https://raw.githubusercontent.com/${repoSlug}/${encodeURIComponent(repoMeta.default_branch || "main")}/package.json`,
        { headers: { "User-Agent": "Kurox-SecurityAudit/1.0" }, signal: AbortSignal.timeout(5000) },
      );
      if (pkgRes.ok) {
        const pkg = await pkgRes.json();
        const scripts = Object.entries(pkg.scripts || {});
        const riskyInstall = scripts.filter(
          ([k, v]) => ["preinstall", "postinstall", "install"].includes(k) && /(curl|wget|powershell|bash\s+-c|eval\()/i.test(String(v)),
        );
        if (riskyInstall.length > 0) {
          score -= 30;
          findings.push({
            severity: "HIGH",
            check: "npm_lifecycle_scripts",
            message: `Potentially dangerous npm lifecycle script(s): ${riskyInstall.map(([k]) => k).join(", ")}`,
          });
        }
        const deps = Object.entries({ ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) });
        const unpinned = deps.filter(([, ver]) => ver === "*" || String(ver).toLowerCase() === "latest").map(([n]) => n);
        if (unpinned.length > 0) {
          score -= 12;
          findings.push({
            severity: "MEDIUM",
            check: "dependency_pinning",
            message: `Unpinned wildcard/* or latest dependencies: ${unpinned.slice(0, 6).join(", ")}`,
          });
        }
      }
    } catch {
      // Optional deep check skipped on transient fetch error
    }
  }

  // Inspect README.md for CanaryGuard-style hidden prompt injection / zero-width chars
  const readmeFile = [...fileNames].find((n) => n === "readme.md");
  if (readmeFile) {
    try {
      const rmRes = await fetch(
        `https://raw.githubusercontent.com/${repoSlug}/${encodeURIComponent(repoMeta.default_branch || "main")}/README.md`,
        { headers: { "User-Agent": "Kurox-SecurityAudit/1.0" }, signal: AbortSignal.timeout(5000) },
      );
      if (rmRes.ok) {
        const txt = await rmRes.text();
        const hasZeroWidth = /[\u200B-\u200D\uFEFF]/.test(txt);
        const hasInjection = /\b(ignore\s+(all\s+)?(previous|prior)\s+instructions|system\s*:\s*you\s+are)\b/i.test(txt);
        const hasTokenLeak = /\b(sk_live_[0-9a-zA-Z]{16,}|ghp_[0-9A-Za-z]{20,}|AKIA[0-9A-Z]{16})\b/.test(txt);
        if (hasZeroWidth || hasInjection) {
          score -= 25;
          findings.push({
            severity: "HIGH",
            check: "canaryguard_prompt_injection",
            message: "Hidden zero-width characters or prompt-injection override pattern detected in README.md.",
          });
        }
        if (hasTokenLeak) {
          score -= 35;
          findings.push({
            severity: "CRITICAL",
            check: "hardcoded_credential_leak",
            message: "Credential-like API secret pattern matched inside README.md.",
          });
        }
      }
    } catch {
      // Optional deep check
    }
  }

  return {
    target_kind: "github_repository",
    target: repoSlug,
    score: Math.max(0, Math.min(100, score)),
    checks_executed: [
      "github_repository_metadata",
      "root_sensitive_file_scan",
      "security_policy_and_license",
      "package_json_supply_chain",
      "canaryguard_readme_injection_scan",
    ],
    metadata: {
      url: repoMeta.html_url,
      default_branch: repoMeta.default_branch,
      stars: repoMeta.stargazers_count || 0,
      language: repoMeta.language || null,
      archived: Boolean(repoMeta.archived),
      open_issues: repoMeta.open_issues_count || 0,
      mcp_manifest_present: fileNames.has("server.json") || fileNames.has("glama.json") || fileNames.has("mcpize.json"),
    },
    findings,
  };
}

async function auditEvmContract(address) {
  const norm = address.toLowerCase();
  const [rpcRes, goplusBaseRes, dexRes] = await Promise.all([
    fetch("https://mainnet.base.org", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_getCode", params: [norm, "latest"] }),
      signal: AbortSignal.timeout(6000),
    }).catch(() => null),
    fetch(`https://api.gopluslabs.io/api/v1/token_security/8453?contract_addresses=${norm}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(8000),
    }).catch(() => null),
    fetch(`https://api.dexscreener.com/latest/dex/tokens/${norm}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(6000),
    }).catch(() => null),
  ]);

  let bytecodeHex = "0x";
  if (rpcRes && rpcRes.ok) {
    const rpcJson = await rpcRes.json().catch(() => ({}));
    if (typeof rpcJson.result === "string") bytecodeHex = rpcJson.result;
  }

  const goplusJson = goplusBaseRes && goplusBaseRes.ok ? await goplusBaseRes.json().catch(() => ({})) : {};
  let sec = goplusJson?.result?.[norm] || null;
  let detectedChain = bytecodeHex && bytecodeHex !== "0x" ? "base (eip155:8453)" : "evm";

  if (!sec && (!bytecodeHex || bytecodeHex === "0x")) {
    const gpEth = await fetch(`https://api.gopluslabs.io/api/v1/token_security/1?contract_addresses=${norm}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(6000),
    }).catch(() => null);
    const ethJson = gpEth && gpEth.ok ? await gpEth.json().catch(() => ({})) : {};
    sec = ethJson?.result?.[norm] || null;
    if (sec) detectedChain = "ethereum (eip155:1)";
  }

  const dexJson = dexRes && dexRes.ok ? await dexRes.json().catch(() => ({})) : {};
  const pairs = Array.isArray(dexJson?.pairs) ? dexJson.pairs : [];

  if ((!bytecodeHex || bytecodeHex === "0x") && !sec && pairs.length === 0) {
    const err = new Error(`No deployed EVM contract bytecode or token metadata found for '${address}' on Base Mainnet.`);
    err.httpStatus = 404;
    throw err;
  }

  let score = 100;
  const findings = [];
  if (sec) {
    if (String(sec.is_honeypot) === "1" || String(sec.cannot_sell_all) === "1") {
      score -= 60;
      findings.push({ severity: "CRITICAL", check: "rugshield_honeypot", message: "Contract exhibits honeypot / sell-lock behavior." });
    }
    const buyTax = Number(sec.buy_tax || 0) * 100;
    const sellTax = Number(sec.sell_tax || 0) * 100;
    if (sellTax > 10 || buyTax > 10) {
      score -= 25;
      findings.push({ severity: "HIGH", check: "transfer_tax", message: `High swap tax detected (buy=${buyTax.toFixed(1)}%, sell=${sellTax.toFixed(1)}%).` });
    }
    if (String(sec.is_open_source) === "0") {
      score -= 20;
      findings.push({ severity: "MEDIUM", check: "source_verification", message: "Contract source code is not verified open-source." });
    }
    if (String(sec.is_mintable) === "1" || String(sec.can_take_back_ownership) === "1") {
      score -= 15;
      findings.push({ severity: "MEDIUM", check: "privilege_escalation", message: "Privileged minting or ownership reclaim function detected." });
    }
    const creatorPct = Number(sec.creator_percent || 0) * 100;
    if (creatorPct > 15) {
      score -= 15;
      findings.push({ severity: "HIGH", check: "creator_concentration", message: `Deployer wallet holds ${creatorPct.toFixed(1)}% of token supply.` });
    }
  } else {
    findings.push({ severity: "INFO", check: "goplus_coverage", message: "Bytecode verified on Base RPC; ERC-20 token security registry returned no token record." });
  }

  const topPair = pairs.sort((a, b) => Number(b?.liquidity?.usd || 0) - Number(a?.liquidity?.usd || 0))[0] || null;
  const topLiqUsd = Number(topPair?.liquidity?.usd || 0);
  if (pairs.length > 0 && topLiqUsd < 5000) {
    score -= 10;
    findings.push({ severity: "LOW", check: "dex_liquidity", message: `Thin DEX liquidity ($${topLiqUsd.toFixed(0)} USD).` });
  }

  return {
    target_kind: "evm_contract",
    target: address,
    score: Math.max(0, Math.min(100, score)),
    checks_executed: ["base_rpc_eth_getCode", "goplus_token_security", "dexscreener_pair_liquidity"],
    metadata: {
      chain: detectedChain,
      bytecode_bytes: bytecodeHex && bytecodeHex.length > 2 ? (bytecodeHex.length - 2) / 2 : 0,
      token_symbol: sec?.token_symbol || topPair?.baseToken?.symbol || null,
      token_name: sec?.token_name || topPair?.baseToken?.name || null,
      is_open_source: sec ? String(sec.is_open_source) === "1" : null,
      buy_tax_pct: sec ? Number((Number(sec.buy_tax || 0) * 100).toFixed(2)) : null,
      sell_tax_pct: sec ? Number((Number(sec.sell_tax || 0) * 100).toFixed(2)) : null,
      top_pair_liquidity_usd: topPair ? Number(topLiqUsd.toFixed(2)) : null,
    },
    findings,
  };
}

async function auditSolanaMint(mint) {
  const [rpcRes, rcRes, dexRes] = await Promise.all([
    fetch("https://api.mainnet-beta.solana.com", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getAccountInfo", params: [mint, { encoding: "jsonParsed" }] }),
      signal: AbortSignal.timeout(6000),
    }).catch(() => null),
    fetch(`https://api.rugcheck.xyz/v1/tokens/${encodeURIComponent(mint)}/report/summary`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(7000),
    }).catch(() => null),
    fetch(`https://api.dexscreener.com/latest/dex/tokens/${encodeURIComponent(mint)}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(6000),
    }).catch(() => null),
  ]);

  const rpcJson = rpcRes && rpcRes.ok ? await rpcRes.json().catch(() => ({})) : {};
  const accVal = rpcJson?.result?.value || null;
  const rcJson = rcRes && rcRes.ok ? await rcRes.json().catch(() => ({})) : null;
  const dexJson = dexRes && dexRes.ok ? await dexRes.json().catch(() => ({})) : {};
  const pairs = Array.isArray(dexJson?.pairs) ? dexJson.pairs : [];

  if (!accVal && !rcJson && pairs.length === 0) {
    const err = new Error(`Solana mint or account '${mint}' was not found on Solana Mainnet.`);
    err.httpStatus = 404;
    throw err;
  }

  let score = 100;
  const findings = [];
  const parsedInfo = accVal?.data?.parsed?.info || {};
  if (parsedInfo.freezeAuthority) {
    score -= 20;
    findings.push({ severity: "HIGH", check: "solana_freeze_authority", message: `Active freezeAuthority: ${parsedInfo.freezeAuthority}` });
  }
  if (parsedInfo.mintAuthority) {
    score -= 15;
    findings.push({ severity: "MEDIUM", check: "solana_mint_authority", message: `Active mintAuthority: ${parsedInfo.mintAuthority}` });
  }
  const rcRisks = Array.isArray(rcJson?.risks) ? rcJson.risks : [];
  for (const rk of rcRisks.slice(0, 6)) {
    const sev = String(rk.level || "MEDIUM").toUpperCase();
    score -= sev === "DANGER" || sev === "CRITICAL" ? 25 : 10;
    findings.push({
      severity: sev === "DANGER" ? "HIGH" : sev,
      check: "rugcheck_risk",
      message: `${rk.name || "Risk"}${rk.description ? `: ${rk.description}` : ""}`,
    });
  }

  const topPair = pairs.sort((a, b) => Number(b?.liquidity?.usd || 0) - Number(a?.liquidity?.usd || 0))[0] || null;
  return {
    target_kind: "solana_mint",
    target: mint,
    score: Math.max(0, Math.min(100, score)),
    checks_executed: ["solana_rpc_getAccountInfo", "rugcheck_report_summary", "dexscreener_pair_liquidity"],
    metadata: {
      chain: "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
      token_program: accVal?.owner || rcJson?.tokenProgram || null,
      mint_authority: parsedInfo.mintAuthority || null,
      freeze_authority: parsedInfo.freezeAuthority || null,
      lp_locked_pct: rcJson?.lpLockedPct ?? null,
      token_symbol: topPair?.baseToken?.symbol || null,
      top_pair_liquidity_usd: topPair ? Number(Number(topPair.liquidity?.usd || 0).toFixed(2)) : null,
    },
    findings,
  };
}

function gradeFromScore(score) {
  if (score >= 90) return "A";
  if (score >= 80) return "B";
  if (score >= 65) return "C";
  if (score >= 50) return "D";
  return "F";
}

export async function runInstantSecurityAudit(rawTarget, signingSecret, origin = "https://agentfuel402.ak10082247.workers.dev") {
  const parsed = validateAuditTarget(rawTarget);
  if (!parsed.valid) {
    const err = new Error(parsed.error);
    err.httpStatus = 400;
    throw err;
  }

  let rawResult;
  if (parsed.kind === "github_repo") {
    rawResult = await auditGitHubRepository(parsed.normalized);
  } else if (parsed.kind === "evm_contract") {
    rawResult = await auditEvmContract(parsed.normalized);
  } else {
    rawResult = await auditSolanaMint(parsed.normalized);
  }

  const auditedAt = new Date().toISOString();
  const grade = gradeFromScore(rawResult.score);
  const verdict = rawResult.score >= 80 ? "PASS" : rawResult.score >= 55 ? "WARN" : "CRITICAL_RISK";
  const certificateId = `kurox_cert_${Date.now().toString(36)}`;
  const signPayload = `${certificateId}|${rawResult.target}|${rawResult.score}|${grade}|${verdict}|${auditedAt}`;
  const certificateSignature = (await hmacSha256Hex(signPayload, signingSecret)) || null;

  const badgeParams = new URLSearchParams({
    cid: certificateId,
    target: rawResult.target,
    score: String(rawResult.score),
    grade,
    verdict,
    ts: auditedAt,
  });
  if (certificateSignature) {
    badgeParams.set("sig", certificateSignature);
  }
  const badgeUrl = `${origin}/v1/store/badge?${badgeParams.toString()}`;

  return {
    product: "instant-security-audit",
    certificate_id: certificateId,
    audited_at: auditedAt,
    verdict,
    grade,
    ...rawResult,
    certificate_signature: certificateSignature,
    readme_badge_url: badgeUrl,
    readme_badge_markdown: `[![Kurox Security Audit ${grade} (${rawResult.score}/100)](${badgeUrl})](${origin}/store)`,
  };
}

export async function verifyAndRenderSignedAuditBadge(searchParams, secret) {
  const cid = (searchParams.get("cid") || "").trim();
  const target = (searchParams.get("target") || "").trim();
  const score = (searchParams.get("score") || "").trim();
  const grade = (searchParams.get("grade") || "").trim();
  const verdict = (searchParams.get("verdict") || "").trim();
  const ts = (searchParams.get("ts") || "").trim();
  const sig = (searchParams.get("sig") || "").trim();

  if (!cid || !target || !score || !grade || !verdict || !ts || !sig || !cleanSecret(secret)) {
    return null;
  }
  const expected = await hmacSha256Hex(`${cid}|${target}|${score}|${grade}|${verdict}|${ts}`, secret);
  if (!expected || !timingSafeHexEqual(sig, expected)) {
    return null;
  }

  const leftText = `Kurox Audit: ${target.slice(0, 24)}`;
  const rightText = `${grade} (${score}/100 ${verdict})`;
  const color = verdict === "PASS" ? "#059669" : verdict === "WARN" ? "#d97706" : "#dc2626";
  const lW = Math.max(96, leftText.length * 6.8 + 16);
  const rW = Math.max(88, rightText.length * 6.8 + 16);
  const totalW = Math.round(lW + rW);

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${totalW}" height="20" role="img" aria-label="${escStoreHtml(leftText)}: ${escStoreHtml(rightText)}">
  <clipPath id="r"><rect width="${totalW}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="${Math.round(lW)}" height="20" fill="#1e293b"/>
    <rect x="${Math.round(lW)}" width="${Math.round(rW)}" height="20" fill="${color}"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">
    <text x="${Math.round(lW / 2)}" y="14">${escStoreHtml(leftText)}</text>
    <text x="${Math.round(lW + rW / 2)}" y="14">${escStoreHtml(rightText)}</text>
  </g>
</svg>`;
}

export function renderAuditCertificateHtml(report) {
  const rows = (report.findings || []).length
    ? report.findings
        .map(
          (f) => `<tr>
            <td><strong>${escStoreHtml(f.severity)}</strong></td>
            <td><code>${escStoreHtml(f.check)}</code></td>
            <td>${escStoreHtml(f.message)}</td>
          </tr>`,
        )
        .join("")
    : `<tr><td colspan="3">No critical/medium security findings flagged across executed automated checks.</td></tr>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kurox Security Audit Certificate — ${escStoreHtml(report.target)}</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; background: #0b101b; color: #f8fafc; max-width: 860px; margin: 0 auto; padding: 2rem 1.25rem; line-height: 1.55; }
    .cert { background: #131722; border: 2px solid #38bdf8; border-radius: 14px; padding: 1.75rem; }
    .badge-pill { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 999px; font-weight: 800; background: ${report.verdict === "PASS" ? "#059669" : report.verdict === "WARN" ? "#d97706" : "#dc2626"}; color: #fff; }
    table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
    th, td { border: 1px solid #263146; padding: 0.55rem 0.7rem; text-align: left; font-size: 0.9rem; }
    th { background: #1e293b; }
    code, pre { background: #05070c; border: 1px solid #232a3b; border-radius: 6px; padding: 0.35rem 0.55rem; color: #34d399; word-break: break-all; }
    pre { padding: 0.85rem; overflow-x: auto; }
    .print-btn { background: #2563eb; color: #fff; border: 0; border-radius: 8px; padding: 0.65rem 1.1rem; font-weight: 700; cursor: pointer; margin-bottom: 1rem; }
    @media print {
      body { background: #fff; color: #111827; padding: 0; }
      .cert { background: #fff; border-color: #1e293b; }
      .print-btn { display: none; }
      code, pre { background: #f3f4f6; color: #111827; border-color: #d1d5db; }
      th { background: #e5e7eb; color: #111827; }
    }
  </style>
</head>
<body>
  <button class="print-btn" onclick="window.print()">Print / Save PDF Certificate</button>
  <div class="cert">
    <h1>Kurox Automated Security Audit Certificate</h1>
    <p><span class="badge-pill">${escStoreHtml(report.verdict)} &bull; Grade ${escStoreHtml(report.grade)} (${escStoreHtml(report.score)}/100)</span></p>
    <p><strong>Target:</strong> <code>${escStoreHtml(report.target)}</code> (${escStoreHtml(report.target_kind)})<br>
       <strong>Certificate ID:</strong> <code>${escStoreHtml(report.certificate_id)}</code><br>
       <strong>Audited At:</strong> ${escStoreHtml(report.audited_at)}</p>
    <h3>Checks &amp; Findings</h3>
    <table>
      <tr><th>Severity</th><th>Check</th><th>Details</th></tr>
      ${rows}
    </table>
    <h3>Embeddable README Markdown Badge</h3>
    <pre>${escStoreHtml(report.readme_badge_markdown)}</pre>
    <p style="font-size:0.82rem;color:#94a3b8;">HMAC-SHA256 Verification Signature: <code>${escStoreHtml(report.certificate_signature || "unsigned")}</code></p>
  </div>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// STOREFRONT HTML RENDERER (GET /store)
// ---------------------------------------------------------------------------
export function renderStoreHtml(origin) {
  const stats = getStoreSnapshotStats();
  const alphaUpdated = String(stats.base_alpha.compiled_at || "").slice(0, 16).replace("T", " ") + " UTC";
  const leadsUpdated = String(stats.b2b_leads.compiled_at || "").slice(0, 16).replace("T", " ") + " UTC";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AgentFuel402 Intelligence Store — High-AOV Data Packs &amp; Instant Security Audits</title>
  <style>
    :root { color-scheme: dark; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #090a0f; color: #f8fafc; margin: 0 auto; max-width: 1060px; padding: 2rem 1rem 4rem; line-height: 1.55; }
    .top-bar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 1.5rem; }
    h1 { color: #38bdf8; margin: 0; font-size: 2rem; }
    .sub { color: #94a3b8; margin-top: 0.35rem; }
    .pill { display: inline-block; background: #131c2e; border: 1px solid #2b3a55; color: #7dd3fc; border-radius: 999px; padding: 0.2rem 0.65rem; font-size: 0.78rem; margin-right: 0.4rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(305px, 1fr)); gap: 1.15rem; margin: 1.5rem 0; }
    .card { background: #131722; border: 1px solid #242d42; border-radius: 14px; padding: 1.35rem; display: flex; flex-direction: column; justify-content: space-between; }
    .card h2 { margin: 0 0 0.4rem; font-size: 1.18rem; color: #f8fafc; }
    .price { font-size: 1.65rem; font-weight: 800; color: #34d399; margin: 0.45rem 0; }
    .stats { background: #0b101b; border: 1px solid #1f2937; border-radius: 8px; padding: 0.65rem 0.8rem; font-size: 0.84rem; color: #cbd5e1; margin: 0.75rem 0; }
    .input, select { width: 100%; box-sizing: border-box; background: #070b14; border: 1px solid #334155; color: #f8fafc; border-radius: 8px; padding: 0.55rem 0.7rem; font-size: 0.9rem; margin: 0.35rem 0 0.75rem; }
    .actions { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.75rem; }
    .btn { display: block; text-align: center; padding: 0.68rem 1rem; border-radius: 8px; font-weight: 700; font-size: 0.9rem; text-decoration: none; cursor: pointer; border: 1px solid #334155; background: #1e293b; color: #f8fafc; }
    .btn-stripe { background: #2563eb; border-color: #60a5fa; color: #fff; }
    .btn-x402 { background: #059669; border-color: #10b981; color: #fff; }
    .preview-box { background: #05070c; border: 1px solid #232a3b; border-radius: 10px; padding: 1rem; margin-top: 1.25rem; }
    pre { overflow-x: auto; font-size: 0.8rem; color: #38bdf8; max-height: 280px; margin: 0.5rem 0 0; }
    a { color: #38bdf8; }
  </style>
</head>
<body>
  <div class="top-bar">
    <div>
      <h1>AgentFuel402 Intelligence Store</h1>
      <p class="sub">High-signal compiled datasets &amp; instant security certificates. Instant delivery via <strong>Stripe</strong> or <strong>Base / Solana USDC (x402)</strong>.</p>
    </div>
    <div>
      <a class="btn" href="${escStoreHtml(origin)}/">Back to API Hub</a>
    </div>
  </div>

  <div>
    <span class="pill">Stripe Instant Download</span>
    <span class="pill">Base + Solana Gasless USDC (x402 V2)</span>
    <span class="pill">Zero Account Signup Required</span>
    <span class="pill">JSON + CSV + Printable PDF Certificate</span>
  </div>

  <div class="grid">
    <!-- Product A -->
    <div class="card" id="product-base-alpha">
      <div>
        <h2>1. Base &amp; Solana Launch Alpha Feed</h2>
        <div class="price">$29.00 <span style="font-size:0.9rem;color:#94a3b8;font-weight:500;">USD / USDC</span></div>
        <p style="font-size:0.9rem;color:#cbd5e1;">Daily-compiled drop of newly deployed Base Mainnet &amp; Solana token pools with DEX liquidity metrics, GoPlus/RugCheck deployer risk analysis &amp; social links (+30d API Key).</p>
        <div class="stats">
          <strong>Live Snapshot:</strong> ${escStoreHtml(stats.base_alpha.total_tokens)} tokens (${escStoreHtml(stats.base_alpha.base_count)} Base, ${escStoreHtml(stats.base_alpha.solana_count)} Solana, ${escStoreHtml(stats.base_alpha.over_10k_liquidity_count)} &gt;$10k liq)<br>
          <strong>Updated:</strong> ${escStoreHtml(alphaUpdated)}
        </div>
        <label for="fmt-alpha" style="font-size:0.82rem;color:#94a3b8;">Preferred Format</label>
        <select id="fmt-alpha">
          <option value="csv">CSV Spreadsheet (.csv)</option>
          <option value="json">Structured JSON (.json)</option>
        </select>
      </div>
      <div class="actions">
        <button class="btn btn-stripe" onclick="buyStripe('base-alpha-feed', 'fmt-alpha')">Buy Now with Card ($29 Stripe)</button>
        <button class="btn btn-x402" onclick="inspectX402('base-alpha-feed', 'fmt-alpha')">Pay $29.00 USDC via x402 (Base / Solana)</button>
        <button class="btn" onclick="loadStorePreview('base-alpha-feed')">Preview 2 Live Tokens</button>
      </div>
    </div>

    <!-- Product B -->
    <div class="card" id="product-b2b-leads">
      <div>
        <h2>2. Fresh AI &amp; SaaS Startup Intent Leads (500)</h2>
        <div class="price">$39.00 <span style="font-size:0.9rem;color:#94a3b8;font-weight:500;">USD / USDC</span></div>
        <p style="font-size:0.9rem;color:#cbd5e1;">Compiled database of up to 500 newly launched AI startups, HN Show/Hiring leads, Remotive hirers &amp; fresh GitHub AI/MCP repos with stack tags (+30d API Key).</p>
        <div class="stats">
          <strong>Live Snapshot:</strong> ${escStoreHtml(stats.b2b_leads.total_leads)} verified startups (${escStoreHtml(stats.b2b_leads.hiring_count)} actively hiring, ${escStoreHtml(stats.b2b_leads.verified_email_count)} published emails)<br>
          <strong>Updated:</strong> ${escStoreHtml(leadsUpdated)}
        </div>
        <label for="fmt-leads" style="font-size:0.82rem;color:#94a3b8;">Preferred Format</label>
        <select id="fmt-leads">
          <option value="csv">CSV Spreadsheet (.csv)</option>
          <option value="json">Structured JSON (.json)</option>
        </select>
      </div>
      <div class="actions">
        <button class="btn btn-stripe" onclick="buyStripe('b2b-startup-leads-500', 'fmt-leads')">Buy Now with Card ($39 Stripe)</button>
        <button class="btn btn-x402" onclick="inspectX402('b2b-startup-leads-500', 'fmt-leads')">Pay $39.00 USDC via x402 (Base / Solana)</button>
        <button class="btn" onclick="loadStorePreview('b2b-startup-leads-500')">Preview 2 Live Leads</button>
      </div>
    </div>

    <!-- Product C -->
    <div class="card" id="product-security-audit">
      <div>
        <h2>3. Instant Contract / MCP Security Audit</h2>
        <div class="price">$9.99 <span style="font-size:0.9rem;color:#94a3b8;font-weight:500;">USD / USDC</span></div>
        <p style="font-size:0.9rem;color:#cbd5e1;">Runs automated Base/Solana/GoPlus/RugCheck or GitHub README + supply-chain audit checks and issues a signed JSON, Printable PDF Certificate &amp; README SVG Badge.</p>
        <label for="audit-target" style="font-size:0.82rem;color:#94a3b8;">GitHub Repo (owner/repo or URL) or Contract/Mint Address</label>
        <input id="audit-target" class="input" type="text" value="modelcontextprotocol/servers" placeholder="owner/repo, https://github.com/..., or 0x..." />
      </div>
      <div class="actions">
        <button class="btn btn-stripe" onclick="buyAuditStripe()">Run Audit &amp; Pay ($9.99 Stripe)</button>
        <button class="btn btn-x402" onclick="inspectX402('instant-security-audit', null, true)">Pay $9.99 USDC via x402 (Base / Solana)</button>
      </div>
    </div>
  </div>

  <div class="preview-box">
    <strong>Live Store Output &amp; x402 Challenge Inspector</strong>
    <pre id="storeOut">Click any Preview or "Pay via x402" button above to inspect live dataset samples or exact Base/Solana x402 payment instructions...</pre>
  </div>

  <script>
    function buyStripe(sku, fmtElId) {
      const fmt = document.getElementById(fmtElId)?.value || "json";
      window.location.href = "/v1/store/checkout?sku=" + encodeURIComponent(sku) + "&format=" + encodeURIComponent(fmt);
    }
    function buyAuditStripe() {
      const target = (document.getElementById("audit-target")?.value || "").trim();
      if (!target) {
        alert("Enter a GitHub repo (owner/repo), Base 0x address, or Solana mint address first.");
        return;
      }
      window.location.href = "/v1/store/checkout?sku=instant-security-audit&target=" + encodeURIComponent(target);
    }
    async function loadStorePreview(sku) {
      const out = document.getElementById("storeOut");
      out.textContent = "Loading live sample for " + sku + "...";
      try {
        const res = await fetch("/v1/store/preview?sku=" + encodeURIComponent(sku));
        out.textContent = JSON.stringify(await res.json(), null, 2);
      } catch (e) {
        out.textContent = "Preview failed: " + e.message;
      }
    }
    async function inspectX402(sku, fmtElId, isAudit) {
      const out = document.getElementById("storeOut");
      const fmt = fmtElId ? (document.getElementById(fmtElId)?.value || "json") : "json";
      const target = isAudit ? (document.getElementById("audit-target")?.value || "").trim() : "";
      let url = "/v1/store/buy?sku=" + encodeURIComponent(sku) + "&format=" + encodeURIComponent(fmt);
      if (isAudit) url += "&target=" + encodeURIComponent(target);
      out.textContent = "Fetching live HTTP 402 dual-chain quote for " + sku + "...";
      try {
        const res = await fetch(url, { method: "POST" });
        const body = await res.json();
        out.textContent = "HTTP " + res.status + " x402 V2 Challenge (" + url + "):\\n\\n" + JSON.stringify(body, null, 2);
      } catch (e) {
        out.textContent = "Failed: " + e.message;
      }
    }
  </script>
</body>
</html>`;
}
