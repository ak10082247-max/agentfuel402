/**
 * Kurox Stripe Instant Fulfillment, Checkout Session Creator & Unified HMAC Bearer API Keys.
 * Pure Web Standards (crypto.subtle / Uint8Array / TextEncoder) — zero external deps, $0/mo on Cloudflare Workers & Node 24+.
 */

import { BUNDLE_ZIPS } from "./bundles.js";

const enc = new TextEncoder();
const dec = new TextDecoder();

export const API_KEY_PLANS = {
  starter: {
    id: "starter",
    sku: "kurox-api-starter-30d",
    name: "Kurox Unified API Key — Starter (30 Days)",
    description:
      "Direct HTTP & MCP Bearer API key across AgentFuel402 (all 5 feeds), CanaryGuard 402, and RugShield 402 — zero x402 crypto wallet required.",
    amountCents: 500,
    priceDisplay: "$5 USD",
    ttlSeconds: 30 * 24 * 60 * 60,
    tier: "starter",
  },
  pro: {
    id: "pro",
    sku: "kurox-api-pro-90d",
    name: "Kurox Unified API Key — Pro (90 Days)",
    description:
      "90-day high-priority HTTP & MCP Bearer API key across AgentFuel402, CanaryGuard 402, and RugShield 402.",
    amountCents: 1900,
    priceDisplay: "$19 USD",
    ttlSeconds: 90 * 24 * 60 * 60,
    tier: "pro",
  },
};

export const BUNDLE_SKUS = {
  canaryguard: {
    sku: "canaryguard-firewall-proxy-v1",
    priceId: "price_1Uc5u0DmOa2iw8hhmbGXISLC",
    name: "CanaryGuard AI Firewall Proxy v1.0.0",
    priceDisplay: "$9 USD",
    zips: ["canaryguard-firewall-proxy-v1"],
    bonusApiTtlSeconds: 30 * 24 * 60 * 60,
    tier: "bundle_canaryguard",
  },
  rugshield: {
    sku: "rugshield-pretrade-scanner-v1",
    priceId: "price_1Uc5uADmOa2iw8hhJ6bgRfYw",
    name: "RugShield Pre-Trade Scanner v1.0.0",
    priceDisplay: "$9 USD",
    zips: ["rugshield-pretrade-scanner-v1"],
    bonusApiTtlSeconds: 30 * 24 * 60 * 60,
    tier: "bundle_rugshield",
  },
  dual: {
    sku: "kurox-security-suite-bundle-v1",
    priceId: "price_1Uc5uGDmOa2iw8hhUDSzdTQc",
    name: "Kurox Dual Security Bundle v1.0.0 (CanaryGuard + RugShield)",
    priceDisplay: "$15 USD",
    zips: ["canaryguard-firewall-proxy-v1", "rugshield-pretrade-scanner-v1"],
    bonusApiTtlSeconds: 60 * 24 * 60 * 60,
    tier: "bundle_dual",
  },
};

export const DATA_PACK_PLANS = {
  "csv-pack": {
    id: "csv-pack",
    sku: "b2b-tech-intent-leads-csv-v1",
    name: "Live B2B Tech Intent & Hiring Leads Pack (.csv)",
    description:
      "Fresh, non-cached CSV export of 25 newly launched tech/AI companies, domains, tech stacks, hiring flags & intent scores + 30-day Starter API key.",
    amountCents: 1900,
    priceDisplay: "$19 USD",
    filename: "Kurox_B2B_Tech_Intent_Leads_Live.csv",
    bonusApiTtlSeconds: 30 * 24 * 60 * 60,
    tier: "data_pack",
  },
};

const PRICE_ID_TO_BUNDLE = Object.fromEntries(
  Object.values(BUNDLE_SKUS).map((b) => [b.priceId, b]),
);

function toBase64Url(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64UrlToBytes(b64url) {
  const padded = b64url.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((b64url.length + 3) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

export function decodeBase64ToBytes(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function cleanSecret(value) {
  return typeof value === "string" ? value.replace(/[\uFEFF\x00-\x20\x7F]+/g, "") : "";
}

async function importHmacKey(secret) {
  const normalized = cleanSecret(secret);
  if (!normalized || normalized.length < 16) {
    throw new Error("KUROX_SIGNING_SECRET is not configured.");
  }
  return await crypto.subtle.importKey(
    "raw",
    enc.encode(normalized),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

export async function signKuroxToken(payload, secret, prefix = "sk_kurox_v1") {
  const key = await importHmacKey(secret);
  const bodyB64 = toBase64Url(enc.encode(JSON.stringify(payload)));
  const signedData = `${prefix}.${bodyB64}`;
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(signedData));
  return `${signedData}.${toBase64Url(new Uint8Array(sig))}`;
}

export async function verifyKuroxToken(token, secret, expectedPrefix = "sk_kurox_v1") {
  if (!token || typeof token !== "string" || !secret) return null;
  const parts = token.trim().split(".");
  if (parts.length !== 3 || parts[0] !== expectedPrefix) return null;
  const [prefix, bodyB64, sigB64] = parts;
  if (!bodyB64 || !sigB64) return null;

  try {
    const key = await importHmacKey(secret);
    const sigBytes = fromBase64UrlToBytes(sigB64);
    const ok = await crypto.subtle.verify("HMAC", key, sigBytes, enc.encode(`${prefix}.${bodyB64}`));
    if (!ok) return null;
    const payload = JSON.parse(dec.decode(fromBase64UrlToBytes(bodyB64)));
    const now = Math.floor(Date.now() / 1000);
    if (typeof payload.exp !== "number" || payload.exp <= now) return null;
    return payload;
  } catch {
    return null;
  }
}

/**
 * Inspects Authorization: Bearer sk_kurox_v1... or X-API-Key: sk_kurox_v1...
 * Returns { present: false } if absent, { present: true, valid: true, payload } if valid,
 * or { present: true, valid: false, error } if malformed/expired/unconfigured.
 */
export async function authenticateBearerApiKey(req, env) {
  const auth = req.headers.get("Authorization") || req.headers.get("authorization") || "";
  const xApiKey = req.headers.get("X-API-Key") || req.headers.get("x-api-key") || "";
  const rawToken = auth.startsWith("Bearer ") ? auth.slice(7).trim() : xApiKey.trim();

  if (!rawToken) return { present: false, valid: false };
  if (!rawToken.startsWith("sk_kurox_v1.")) {
    return { present: true, valid: false, error: "Unsupported API key prefix. Expected sk_kurox_v1.*" };
  }
  if (!env?.KUROX_SIGNING_SECRET) {
    return { present: true, valid: false, error: "API key verification temporarily unavailable", status: 503 };
  }
  const payload = await verifyKuroxToken(rawToken, env.KUROX_SIGNING_SECRET, "sk_kurox_v1");
  if (!payload || payload.typ !== "api_key") {
    return { present: true, valid: false, error: "Invalid or expired Kurox API key", status: 401 };
  }
  return { present: true, valid: true, payload };
}

export async function verifyStripeWebhookSignature(rawBody, sigHeader, webhookSecret) {
  if (!webhookSecret) throw new Error("STRIPE_WEBHOOK_SECRET not configured");
  if (!sigHeader) return false;

  let timestamp = null;
  const v1Sigs = [];
  for (const part of sigHeader.split(",")) {
    const [k, v] = part.split("=").map((s) => s.trim());
    if (k === "t") timestamp = v;
    if (k === "v1" && v) v1Sigs.push(v);
  }
  if (!timestamp || v1Sigs.length === 0) return false;
  const tsNum = Number(timestamp);
  if (!Number.isFinite(tsNum) || Math.abs(Math.floor(Date.now() / 1000) - tsNum) > 300) {
    return false;
  }

  const key = await importHmacKey(webhookSecret);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(`${timestamp}.${rawBody}`)));
  const expectedHex = Array.from(mac)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return v1Sigs.some((sig) => {
    if (sig.length !== expectedHex.length) return false;
    let diff = 0;
    for (let i = 0; i < expectedHex.length; i += 1) {
      diff |= sig.charCodeAt(i) ^ expectedHex.charCodeAt(i);
    }
    return diff === 0;
  });
}

function appendFormParams(params, obj, prefix = "") {
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null) continue;
    const key = prefix ? `${prefix}[${k}]` : k;
    if (Array.isArray(v)) {
      v.forEach((item, idx) => {
        if (typeof item === "object" && item !== null) {
          appendFormParams(params, item, `${key}[${idx}]`);
        } else {
          params.append(`${key}[${idx}]`, String(item));
        }
      });
    } else if (typeof v === "object") {
      appendFormParams(params, v, key);
    } else {
      params.append(key, String(v));
    }
  }
}

export async function createStripeCheckoutSession(options, env) {
  const stripeKey = cleanSecret(env?.STRIPE_SECRET_KEY);
  if (!stripeKey) {
    throw Object.assign(new Error("Stripe checkout not configured on worker"), { httpStatus: 503 });
  }
  const form = new URLSearchParams();
  appendFormParams(form, {
    mode: "payment",
    customer_creation: "always",
    success_url: options.successUrl,
    cancel_url: options.cancelUrl,
    line_items: options.lineItems,
    metadata: options.metadata,
  });

  const res = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${stripeKey}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: form.toString(),
    signal: AbortSignal.timeout(15000),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.url) {
    throw Object.assign(new Error(data.error?.message || `Stripe API error HTTP ${res.status}`), {
      httpStatus: 502,
    });
  }
  return data;
}

function resolveCatalogItemFromSession(session) {
  const metaSku = session.metadata?.sku || "";
  const metaKind = session.metadata?.kind || "";
  const lineItem = session.line_items?.data?.[0];
  const priceId = lineItem?.price?.id || "";

  if (PRICE_ID_TO_BUNDLE[priceId]) {
    return { kind: "bundle", item: PRICE_ID_TO_BUNDLE[priceId] };
  }
  for (const d of Object.values(DATA_PACK_PLANS)) {
    if (metaSku === d.sku) return { kind: "data_pack", item: d };
  }
  for (const b of Object.values(BUNDLE_SKUS)) {
    if (metaSku === b.sku) return { kind: "bundle", item: b };
  }
  for (const p of Object.values(API_KEY_PLANS)) {
    if (metaSku === p.sku) return { kind: "api_key", item: p };
  }
  if (session.amount_total === 1900 && metaKind === "data_pack") return { kind: "data_pack", item: DATA_PACK_PLANS["csv-pack"] };
  if (session.amount_total === 1900) return { kind: "api_key", item: API_KEY_PLANS.pro };
  if (session.amount_total === 500) return { kind: "api_key", item: API_KEY_PLANS.starter };
  if (session.amount_total === 1500) return { kind: "bundle", item: BUNDLE_SKUS.dual };
  return { kind: "api_key", item: API_KEY_PLANS.starter };
}

export async function verifyCheckoutSessionAndMint(sessionId, origin, env) {
  const stripeKey = cleanSecret(env?.STRIPE_SECRET_KEY);
  const signingSecret = cleanSecret(env?.KUROX_SIGNING_SECRET);
  if (!stripeKey || !signingSecret) {
    throw Object.assign(new Error("Stripe fulfillment secrets not configured on worker"), { httpStatus: 503 });
  }
  if (!/^cs_(test|live)_[A-Za-z0-9_]+$/.test(sessionId || "")) {
    throw Object.assign(new Error("Invalid Stripe Checkout session_id"), { httpStatus: 400 });
  }

  const res = await fetch(
    `https://api.stripe.com/v1/checkout/sessions/${encodeURIComponent(sessionId)}?expand[]=line_items`,
    {
      headers: { Authorization: `Bearer ${stripeKey}` },
      signal: AbortSignal.timeout(15000),
    },
  );
  const session = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw Object.assign(new Error(session.error?.message || `Stripe lookup failed (HTTP ${res.status})`), {
      httpStatus: res.status === 404 ? 404 : 502,
    });
  }
  if (session.payment_status !== "paid") {
    throw Object.assign(new Error(`Payment status is '${session.payment_status || "unpaid"}' (expected paid)`), {
      httpStatus: 402,
    });
  }

  const now = Math.floor(Date.now() / 1000);
  const resolved = resolveCatalogItemFromSession(session);
  const item = resolved.item;
  const apiTtl = resolved.kind === "api_key" ? item.ttlSeconds : item.bonusApiTtlSeconds;

  const apiKey = await signKuroxToken(
    {
      typ: "api_key",
      sid: session.id,
      sku: item.sku,
      tier: item.tier,
      iat: now,
      exp: now + apiTtl,
    },
    env.KUROX_SIGNING_SECRET,
    "sk_kurox_v1",
  );

  const downloads = [];
  if (resolved.kind === "data_pack") {
    const dlToken = await signKuroxToken(
      {
        typ: "download",
        sid: session.id,
        bundle: item.sku,
        iat: now,
        exp: now + 7 * 24 * 60 * 60,
      },
      env.KUROX_SIGNING_SECRET,
      "dl_v1",
    );
    downloads.push({
      sku: item.sku,
      title: item.name,
      filename: item.filename,
      bytes: null,
      url: `${origin}/v1/stripe/download?token=${encodeURIComponent(dlToken)}`,
    });
  } else if (resolved.kind === "bundle") {
    for (const bundleKey of item.zips) {
      const zipMeta = BUNDLE_ZIPS[bundleKey];
      if (!zipMeta) continue;
      const dlToken = await signKuroxToken(
        {
          typ: "download",
          sid: session.id,
          bundle: bundleKey,
          iat: now,
          exp: now + 7 * 24 * 60 * 60,
        },
        env.KUROX_SIGNING_SECRET,
        "dl_v1",
      );
      downloads.push({
        sku: bundleKey,
        title: zipMeta.title,
        filename: zipMeta.filename,
        bytes: zipMeta.byteLength,
        url: `${origin}/v1/stripe/download?token=${encodeURIComponent(dlToken)}`,
      });
    }
  }

  return {
    paid: true,
    session_id: session.id,
    customer_email: session.customer_details?.email || null,
    amount_total_cents: session.amount_total,
    currency: (session.currency || "usd").toUpperCase(),
    sku: item.sku,
    product_name: item.name,
    api_key: apiKey,
    api_key_expires_at: new Date((now + apiTtl) * 1000).toISOString(),
    downloads,
  };
}

export function renderFulfillmentHtml(fulfillment, origin) {
  const downloadCards = fulfillment.downloads.length
    ? fulfillment.downloads
        .map(
          (d) => `<div class="dl-row">
            <div>
              <strong>${escapeHtml(d.title)}</strong>
              <div class="meta">${escapeHtml(d.filename)} (${d.bytes ? `${Math.round(d.bytes / 1024)} KB` : "Live CSV Export"}) — Link valid 7 days</div>
            </div>
            <a class="btn btn-green" href="${escapeHtml(d.url)}">Download</a>
          </div>`,
        )
        .join("")
    : `<p class="meta">Digital API Pass activated immediately across AgentFuel402, CanaryGuard 402, and RugShield 402.</p>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kurox Instant Fulfillment — Payment Confirmed</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #090a0f; color: #f8fafc; padding: 2rem 1rem; line-height: 1.6; max-width: 820px; margin: 0 auto; }
    .card { background: #131722; border: 1px solid #232a3b; border-radius: 12px; padding: 1.4rem; margin: 1rem 0; }
    .dl-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.85rem; background: #0b101b; border: 1px solid #1f2937; border-radius: 8px; margin: 0.65rem 0; }
    .btn { display: inline-block; padding: 0.6rem 1.05rem; border-radius: 8px; font-weight: 700; font-size: 0.88rem; text-decoration: none; cursor: pointer; border: 1px solid #334155; background: #2563eb; color: #fff; }
    .btn-green { background: #059669; border-color: #10b981; }
    code, pre { background: #05070c; border: 1px solid #232a3b; border-radius: 8px; padding: 0.75rem; display: block; overflow-x: auto; color: #34d399; font-size: 0.84rem; word-break: break-all; }
    .meta { color: #94a3b8; font-size: 0.86rem; }
  </style>
</head>
<body>
  <h1>Payment Confirmed — Instant Access Unlocked</h1>
  <p class="meta">Product: <strong>${escapeHtml(fulfillment.product_name)}</strong> &bull; Session: <code>${escapeHtml(fulfillment.session_id)}</code></p>

  <div class="card">
    <h3>1. Instant ZIP Downloads</h3>
    ${downloadCards}
  </div>

  <div class="card">
    <h3>2. Unified Developer API Key (Valid until ${escapeHtml(fulfillment.api_key_expires_at)})</h3>
    <p class="meta">Use this Bearer key cleanly without x402 wallets on AgentFuel402 HTTP/MCP routes (and compatible Kurox services):</p>
    <code id="apiKeyCode">${escapeHtml(fulfillment.api_key)}</code>
    <h4>Quick cURL Example</h4>
    <pre>curl -s "${escapeHtml(origin)}/v1/fuel/b2b-intent-leads?limit=5" \\
  -H "Authorization: Bearer ${escapeHtml(fulfillment.api_key)}"</pre>
  </div>

  <p><a class="btn" href="${escapeHtml(origin)}/">Back to AgentFuel402</a> <a class="btn" href="https://ak10082247-max.github.io/products.html">All Kurox Products</a></p>
</body>
</html>`;
}
