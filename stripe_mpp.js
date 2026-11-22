import { cleanSecret, decodeBase64ToBytes, hasSigningSecretConfigured, signKuroxToken } from "./stripe_billing.js";

export const DEFAULT_STRIPE_PROFILE_ID = "profile_61VnzdDTGkNiFINqdA6VnzdDR1E92xUACS0Twn2zoUBE";
export const STRIPE_PREVIEW_VERSION = "2026-07-29.preview";
export const STRIPE_MIN_USD_CENTS = 50;
export const STRIPE_PAYMENT_INTENTS_URL = "https://api.stripe.com/v1/payment_intents";

const MAX_AUTHORIZATION_LENGTH = 64 * 1024;
const INTERNAL_AUTH_SKEW_SECONDS = 300;
const usedChallengeIds = new Set();
const MAX_USED_CHALLENGES = 10_000;

const enc = new TextEncoder();
const dec = new TextDecoder();

export const MPP_PASS_PLANS = {
  pass: {
    id: "pass",
    sku: "kurox-mpp-pass-7d",
    tier: "mpp_pass",
    name: "Kurox Unified 7-Day Multi-Call Pass",
    amountCents: 50,
    priceDisplay: "$0.50 USD",
    durationSeconds: 7 * 24 * 60 * 60,
  },
  starter: {
    id: "starter",
    sku: "kurox-api-starter-30d",
    tier: "starter",
    name: "Kurox Unified Developer API Key - Starter (30d)",
    amountCents: 500,
    priceDisplay: "$5.00 USD",
    durationSeconds: 30 * 24 * 60 * 60,
  },
  pro: {
    id: "pro",
    sku: "kurox-api-pro-90d",
    tier: "pro",
    name: "Kurox Unified Developer API Key - Pro (90d)",
    amountCents: 1900,
    priceDisplay: "$19.00 USD",
    durationSeconds: 90 * 24 * 60 * 60,
  },
};

export function toBase64Utf8(str) {
  const bytes = enc.encode(String(str ?? ""));
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

export const ALLOWED_INTERNAL_REALMS = new Set([
  "agentfuel402.ak10082247.workers.dev",
  "canaryguard-402.onrender.com",
  "rugshield-402.onrender.com",
]);

function toBase64Url(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64UrlToString(b64url) {
  const padded = String(b64url || "").replace(/-/g, "+").replace(/_/g, "/") + "===".slice((String(b64url || "").length + 3) % 4);
  return dec.decode(decodeBase64ToBytes(padded));
}

function encodeJsonBase64Url(value) {
  return toBase64Url(enc.encode(JSON.stringify(value)));
}

/**
 * Deterministic RFC-style canonical JSON matching ox/Json.canonicalize for Challenge binding.
 */
export function canonicalJson(value) {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => (item === undefined ? "null" : canonicalJson(item))).join(",")}]`;
  }
  const keys = Object.keys(value)
    .filter((k) => value[k] !== undefined)
    .sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(",")}}`;
}

export function encodeCanonicalRequest(requestObj) {
  return toBase64Url(enc.encode(canonicalJson(requestObj)));
}

function constantTimeEqual(a, b) {
  const sa = String(a || "");
  const sb = String(b || "");
  if (sa.length !== sb.length || sa.length === 0) return false;
  let diff = 0;
  for (let i = 0; i < sa.length; i += 1) {
    diff |= sa.charCodeAt(i) ^ sb.charCodeAt(i);
  }
  return diff === 0;
}

function rememberUsedChallenge(challengeId) {
  if (!challengeId) return;
  if (usedChallengeIds.size >= MAX_USED_CHALLENGES) {
    const oldest = usedChallengeIds.values().next().value;
    if (oldest) usedChallengeIds.delete(oldest);
  }
  usedChallengeIds.add(challengeId);
}

async function importSigningKey(secret) {
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

export function resolveStripeProfileId(env) {
  const configured = cleanSecret(env?.STRIPE_PROFILE_ID);
  return configured || DEFAULT_STRIPE_PROFILE_ID;
}

export function getStripeMppChallengeInput(challenge) {
  const encodedReq = typeof challenge.request === "string"
    ? challenge.request
    : encodeCanonicalRequest(challenge.request || {});
  const values = [
    String(challenge.realm || ""),
    String(challenge.method || ""),
    String(challenge.intent || ""),
    encodedReq,
    challenge.expires ? String(challenge.expires) : "",
    challenge.digest ? String(challenge.digest) : "",
  ];
  if (challenge.header && /^payment-authorization$/i.test(challenge.header)) {
    values.push(challenge.header);
  }
  const encodedOpaque = challenge.opaque
    ? String(challenge.opaque)
    : challenge.meta
      ? encodeCanonicalRequest(challenge.meta)
      : "";
  values.push(encodedOpaque);
  return values.join("|");
}

export async function computeChallengeId(challenge, secret) {
  const key = await importSigningKey(secret);
  const input = getStripeMppChallengeInput(challenge);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(input));
  return toBase64Url(new Uint8Array(sig));
}

function authParam(name, value) {
  const str = String(value ?? "");
  if (/[\r\n]/.test(str)) {
    throw new Error(`Invalid quoted-string header value for ${name}`);
  }
  const escaped = str
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/[\u0100-\uffff]/g, (ch) => `\\u${ch.charCodeAt(0).toString(16).padStart(4, "0")}`);
  return `${name}="${escaped}"`;
}

/**
 * Builds an mppx@0.21.1-compatible Stripe charge challenge & WWW-Authenticate header.
 */
export async function buildStripeChargeChallenge({
  realm,
  amountCents = STRIPE_MIN_USD_CENTS,
  currency = "usd",
  description,
  networkId = DEFAULT_STRIPE_PROFILE_ID,
  paymentMethodTypes = ["card"],
  expiresIso,
  opaque,
  externalId,
  metadata,
  secretKey,
}) {
  const safeAmount = Math.max(STRIPE_MIN_USD_CENTS, Math.round(Number(amountCents) || STRIPE_MIN_USD_CENTS));
  const safeCurrency = String(currency || "usd").toLowerCase();
  const safeExpires = expiresIso || new Date(Date.now() + 5 * 60 * 1000).toISOString();
  const safeRealm = String(realm || "agentfuel402.ak10082247.workers.dev");
  const safeDesc = description ? String(description).slice(0, 440) : undefined;

  const request = {
    amount: String(safeAmount),
    currency: safeCurrency,
    ...(safeDesc ? { description: safeDesc } : {}),
    ...(externalId !== undefined ? { externalId: String(externalId) } : {}),
    methodDetails: {
      networkId: String(networkId || DEFAULT_STRIPE_PROFILE_ID),
      paymentMethodTypes: Array.isArray(paymentMethodTypes) && paymentMethodTypes.length > 0 ? paymentMethodTypes : ["card"],
      ...(metadata && typeof metadata === "object" ? { metadata } : {}),
    },
  };

  const baseChallenge = {
    realm: safeRealm,
    method: "stripe",
    intent: "charge",
    request,
    ...(safeDesc ? { description: safeDesc } : {}),
    expires: safeExpires,
    ...(opaque !== undefined ? { opaque: String(opaque) } : {}),
  };

  let id;
  if (secretKey && cleanSecret(secretKey).length >= 16) {
    id = await computeChallengeId(baseChallenge, secretKey);
  } else {
    const rnd = new Uint8Array(16);
    crypto.getRandomValues(rnd);
    id = `dev_${toBase64Url(rnd)}`;
  }

  const challenge = { id, ...baseChallenge };
  const requestB64 = encodeCanonicalRequest(request);
  const parts = [
    authParam("id", challenge.id),
    authParam("realm", challenge.realm),
    authParam("method", challenge.method),
    authParam("intent", challenge.intent),
    authParam("request", requestB64),
  ];
  if (challenge.description) parts.push(authParam("description", challenge.description));
  if (challenge.expires) parts.push(authParam("expires", challenge.expires));
  if (challenge.opaque) parts.push(authParam("opaque", challenge.opaque));

  return {
    challenge,
    requestEncoded: requestB64,
    headerValue: `Payment ${parts.join(", ")}`,
  };
}

/**
 * Extracts `Payment <b64url>` from Authorization or Payment-Authorization headers.
 */
export function extractPaymentSchemeHeader(req) {
  for (const hdrName of ["Payment-Authorization", "Authorization"]) {
    const raw = req.headers.get(hdrName);
    if (!raw || raw.length > MAX_AUTHORIZATION_LENGTH) continue;
    const schemes = raw.split(",").map((s) => s.trim());
    const match = schemes.find((s) => /^Payment\s+\S+/i.test(s));
    if (match) return match;
  }
  return null;
}

/**
 * Normalizes a decoded MPP credential object whose challenge.request may be base64url or an object.
 */
export function normalizeCredentialObject(rawCredential) {
  if (!rawCredential || typeof rawCredential !== "object" || !rawCredential.challenge || typeof rawCredential.challenge !== "object") {
    throw new Error("Credential missing challenge object");
  }
  const rawChallenge = rawCredential.challenge;
  let decodedRequest = rawChallenge.request;
  if (typeof rawChallenge.request === "string") {
    try {
      decodedRequest = JSON.parse(fromBase64UrlToString(rawChallenge.request));
    } catch {
      throw new Error("Invalid base64url challenge.request");
    }
  }
  if (!decodedRequest || typeof decodedRequest !== "object") {
    throw new Error("Invalid challenge.request payload");
  }
  const challenge = {
    ...rawChallenge,
    request: decodedRequest,
  };
  if (typeof rawChallenge.request === "string") {
    challenge._rawRequestB64 = rawChallenge.request;
  }
  return {
    challenge,
    payload: rawCredential.payload || {},
    ...(rawCredential.source ? { source: rawCredential.source } : {}),
  };
}

/**
 * Parses an Authorization: Payment credential token into { challenge, payload, source }.
 */
export function parsePaymentCredentialToken(rawHeader) {
  if (!rawHeader || typeof rawHeader !== "string" || rawHeader.length > MAX_AUTHORIZATION_LENGTH) {
    throw new Error("Missing or oversized Payment credential");
  }
  const m = rawHeader.trim().match(/^Payment\s+([A-Za-z0-9_-]+)$/i);
  if (!m?.[1]) {
    throw new Error("Malformed Payment credential scheme");
  }
  let parsed;
  try {
    parsed = JSON.parse(fromBase64UrlToString(m[1]));
  } catch {
    throw new Error("Invalid base64url JSON Payment credential");
  }
  return normalizeCredentialObject(parsed);
}

/**
 * Verifies challenge HMAC binding, expiration, Stripe parameters, and replay protection.
 */
export async function verifyStripeChallengeAndCredential(credential, env, expectedRealms = null) {
  if (!hasSigningSecretConfigured(env)) {
    throw Object.assign(new Error("MPP challenge verification secret not configured"), { httpStatus: 503 });
  }
  const { challenge, payload } = normalizeCredentialObject(credential);
  if (!challenge || !challenge.id || !challenge.realm) {
    throw Object.assign(new Error("Challenge missing id or realm"), { httpStatus: 402 });
  }
  if (challenge.method !== "stripe" || challenge.intent !== "charge") {
    throw Object.assign(new Error("Unsupported Payment method; expected method=stripe, intent=charge"), { httpStatus: 402 });
  }
  if (expectedRealms) {
    const allowedSet = new Set(Array.from(expectedRealms, (r) => String(r).toLowerCase().replace(/\.$/, "")));
    const realmNorm = String(challenge.realm).toLowerCase().replace(/\.$/, "");
    if (!allowedSet.has(realmNorm)) {
      throw Object.assign(new Error(`Challenge realm mismatch: ${challenge.realm}`), { httpStatus: 402 });
    }
  }
  if (!challenge.expires) {
    throw Object.assign(new Error("Challenge missing expires"), { httpStatus: 402 });
  }
  const expMs = Date.parse(challenge.expires);
  if (!Number.isFinite(expMs) || expMs <= Date.now()) {
    throw Object.assign(new Error("Payment challenge expired"), { httpStatus: 402 });
  }
  if (challenge.header && !/^payment-authorization$/i.test(challenge.header)) {
    throw Object.assign(new Error("Unsupported challenge header field"), { httpStatus: 402 });
  }

  // Verify HMAC-SHA256 binding against KUROX_SIGNING_SECRET using original raw request b64url first (or canonical JSON)
  const expectedId = await computeChallengeId(
    challenge._rawRequestB64
      ? { ...challenge, request: challenge._rawRequestB64 }
      : challenge,
    env.KUROX_SIGNING_SECRET,
  );
  if (!constantTimeEqual(challenge.id, expectedId)) {
    throw Object.assign(new Error("Invalid Payment challenge signature"), { httpStatus: 402 });
  }

  if (usedChallengeIds.has(challenge.id)) {
    throw Object.assign(new Error("Payment challenge already redeemed"), { httpStatus: 402 });
  }

  const reqObj = challenge.request;
  const amountStr = String(reqObj.amount || "");
  if (!/^\d+$/.test(amountStr)) {
    throw Object.assign(new Error("Invalid integer amount in Stripe challenge"), { httpStatus: 402 });
  }
  const amountCents = Number(amountStr);
  const currency = String(reqObj.currency || "").toLowerCase();
  if (currency !== "usd" || amountCents < STRIPE_MIN_USD_CENTS) {
    throw Object.assign(new Error("Stripe card SPT requires currency='usd' and minimum amount >= 50 cents ($0.50)"), { httpStatus: 402 });
  }
  const spt = typeof payload?.spt === "string" ? payload.spt.trim() : "";
  if (!spt || spt.length < 6) {
    throw Object.assign(new Error("Invalid credential payload: missing or malformed spt"), { httpStatus: 402 });
  }
  const reqExtId = reqObj.externalId !== undefined ? String(reqObj.externalId) : undefined;
  const credExtId = payload?.externalId !== undefined ? String(payload.externalId) : undefined;
  if (reqExtId !== undefined && credExtId !== reqExtId) {
    throw Object.assign(new Error("Credential externalId does not match challenge"), { httpStatus: 402 });
  }

  return {
    challenge,
    spt,
    amountCents,
    currency,
    externalId: reqExtId ?? credExtId,
  };
}

/**
 * Determines unified Kurox API pass tier/TTL granted on successful Stripe MPP settlement.
 */
export function resolveMppGrantPlan(amountCents) {
  if (amountCents >= MPP_PASS_PLANS.pro.amountCents) return MPP_PASS_PLANS.pro;
  if (amountCents >= MPP_PASS_PLANS.starter.amountCents) return MPP_PASS_PLANS.starter;
  return MPP_PASS_PLANS.pass;
}

/**
 * Confirms a Shared Payment Token against Stripe /v1/payment_intents and mints a Payment-Receipt + Unified Key.
 */
export async function settleStripeMppCredential({
  credential,
  env,
  serviceSlug = "agentfuel402",
  expectedRealms = null,
  minAmountCents = STRIPE_MIN_USD_CENTS,
  fetchFn = fetch,
}) {
  const verified = await verifyStripeChallengeAndCredential(credential, env, expectedRealms);
  if (verified.amountCents < Number(minAmountCents || STRIPE_MIN_USD_CENTS)) {
    throw Object.assign(new Error(`Insufficient payment amount: required >= ${minAmountCents} cents`), { httpStatus: 402 });
  }

  const stripeSecretKey = cleanSecret(env?.STRIPE_SECRET_KEY);
  if (!stripeSecretKey) {
    throw Object.assign(new Error("Stripe billing secret not configured on worker"), { httpStatus: 503 });
  }

  const { challenge, spt, amountCents, currency, externalId } = verified;
  const body = new URLSearchParams({
    amount: String(amountCents),
    currency,
    confirm: "true",
    "automatic_payment_methods[enabled]": "true",
    "automatic_payment_methods[allow_redirects]": "never",
    shared_payment_granted_token: spt,
    "metadata[machine_payment]": "true",
    "metadata[mpp_intent]": "charge",
    "metadata[mpp_challenge_id]": String(challenge.id).slice(0, 500),
    "metadata[mpp_sdk]": "kurox-mpp@1.0.0",
    "metadata[kurox_service]": String(serviceSlug).slice(0, 100),
    "metadata[kurox_realm]": String(challenge.realm).slice(0, 200),
  });
  if (challenge.request.description) {
    body.set("description", String(challenge.request.description).slice(0, 500));
  }
  const extraMeta = challenge.request.methodDetails?.metadata;
  if (extraMeta && typeof extraMeta === "object") {
    for (const [k, v] of Object.entries(extraMeta)) {
      if (v !== undefined && k !== "externalId" && !body.has(`metadata[${k}]`)) {
        body.set(`metadata[${k}]`, String(v).slice(0, 500));
      }
    }
  }

  const res = await fetchFn(STRIPE_PAYMENT_INTENTS_URL, {
    method: "POST",
    headers: {
      Authorization: `Basic ${btoa(`${stripeSecretKey}:`)}`,
      "Content-Type": "application/x-www-form-urlencoded",
      "Idempotency-Key": `mpp_${challenge.id}_${spt}`,
      "Stripe-Version": STRIPE_PREVIEW_VERSION,
    },
    body: body.toString(),
    signal: AbortSignal.timeout(20_000),
  });

  if (!res.ok) {
    const rawErr = await res.text().catch(() => "");
    let detail = `Stripe PaymentIntent HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(rawErr);
      if (parsed?.error?.message) detail = parsed.error.message;
    } catch {}
    throw Object.assign(new Error(`Stripe PaymentIntent failed: ${detail}`), { httpStatus: 402 });
  }

  if (res.headers?.get?.("idempotent-replayed") === "true") {
    throw Object.assign(new Error("Payment has already been processed."), { httpStatus: 402 });
  }

  const pi = await res.json();
  if (pi.status === "requires_action") {
    throw Object.assign(new Error("Stripe PaymentIntent requires action"), { httpStatus: 402 });
  }
  if (pi.status !== "succeeded") {
    throw Object.assign(new Error(`Stripe PaymentIntent status: ${pi.status}`), { httpStatus: 402 });
  }

  rememberUsedChallenge(challenge.id);

  const nowSec = Math.floor(Date.now() / 1000);
  const receipt = {
    method: "stripe",
    status: "success",
    timestamp: new Date().toISOString(),
    reference: pi.id,
    ...(externalId !== undefined ? { externalId } : {}),
  };
  const receiptHeader = encodeJsonBase64Url(receipt);

  const grant = resolveMppGrantPlan(amountCents);
  const expSec = nowSec + grant.durationSeconds;
  const apiKey = await signKuroxToken(
    {
      typ: "api_key",
      sid: pi.id,
      sku: grant.sku,
      tier: grant.tier,
      mpp: true,
      iat: nowSec,
      exp: expSec,
    },
    env.KUROX_SIGNING_SECRET,
    "sk_kurox_v1",
  );

  return {
    ok: true,
    paymentIntentId: pi.id,
    amountCents,
    currency: currency.toUpperCase(),
    sku: grant.sku,
    tier: grant.tier,
    receipt,
    receiptHeader,
    apiKey,
    apiKeyExpiresAt: new Date(expSec * 1000).toISOString(),
  };
}

/**
 * Verifies internal proxy settlement calls from sibling Kurox services (CanaryGuard / RugShield)
 * using shared KUROX_SIGNING_SECRET HMAC over `${timestamp}.${service}.${rawBody}`.
 */
export async function verifyInternalMppRelayRequest(req, rawBody, env) {
  if (!hasSigningSecretConfigured(env)) {
    throw Object.assign(new Error("Internal relay signing secret unavailable"), { httpStatus: 503 });
  }
  const tsRaw = req.headers.get("X-Kurox-Internal-Timestamp") || "";
  const service = req.headers.get("X-Kurox-Internal-Service") || "";
  const sig = req.headers.get("X-Kurox-Internal-Signature") || "";
  if (!/^\d{10,13}$/.test(tsRaw) || !service || !sig) {
    throw Object.assign(new Error("Missing internal relay authentication headers"), { httpStatus: 401 });
  }
  const tsSec = Number(tsRaw);
  const nowSec = Math.floor(Date.now() / 1000);
  if (!Number.isFinite(tsSec) || Math.abs(nowSec - tsSec) > INTERNAL_AUTH_SKEW_SECONDS) {
    throw Object.assign(new Error("Internal relay signature timestamp expired"), { httpStatus: 401 });
  }
  const key = await importSigningKey(env.KUROX_SIGNING_SECRET);
  const mac = await crypto.subtle.sign("HMAC", key, enc.encode(`${tsRaw}.${service}.${rawBody}`));
  const expectedSig = toBase64Url(new Uint8Array(mac));
  if (!constantTimeEqual(sig, expectedSig)) {
    throw Object.assign(new Error("Invalid internal relay signature"), { httpStatus: 401 });
  }
  return { service, tsSec };
}
