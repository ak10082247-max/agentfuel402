import test from "node:test";
import assert from "node:assert/strict";
import worker from "./worker.js";
import { signKuroxToken } from "./stripe_billing.js";

const ENV = {
  MERCHANT_BASE_ADDRESS: "0x80E0Ae84679b7f11bE171DaADd492FBECf628cd6",
  MERCHANT_SOLANA_ATA: "DD3A7jaXFeHcif9eYj6Vhomuxypat5Yxi8ow6wxz27yL",
  MERCHANT_SOLANA_OWNER: "9wuMysgXwNhtQeqJgGByAiMYc4EjzZ5wUSmnjrrt3ffh",
  SOLANA_FEE_PAYER: "CjNFTjvBhbJJd2B5ePPMHRLx1ELZpa8dwQgGL727eKww",
  PAYAI_FACILITATOR: "https://facilitator.payai.network",
};

const ORIG_FETCH = globalThis.fetch;

test("agentfuel402 landing, pricing, openapi, skill.md, llms.txt & agent-card have no Agency Pass and list reverse-engineer", async () => {
  const [rootRes, priceRes, openapiRes, skillRes, llmsRes, cardRes] = await Promise.all([
    worker.fetch(new Request("https://agentfuel402.ak10082247.workers.dev/"), ENV),
    worker.fetch(new Request("https://agentfuel402.ak10082247.workers.dev/pricing"), ENV),
    worker.fetch(new Request("https://agentfuel402.ak10082247.workers.dev/openapi.json"), ENV),
    worker.fetch(new Request("https://agentfuel402.ak10082247.workers.dev/skill.md"), ENV),
    worker.fetch(new Request("https://agentfuel402.ak10082247.workers.dev/llms.txt"), ENV),
    worker.fetch(new Request("https://agentfuel402.ak10082247.workers.dev/.well-known/agent-card.json"), ENV),
  ]);

  assert.equal(rootRes.status, 200);
  const rootHtml = await rootRes.text();
  assert.doesNotMatch(rootHtml, /#agency-pass|\/v1\/pass\/prepay|Glama Rated B|0ms Cold Start/i);

  assert.equal(priceRes.status, 200);
  const pricing = await priceRes.json();
  assert.equal(pricing.agency_pass, undefined);
  assert.equal(pricing.endpoints.length, 5);

  const openapi = await openapiRes.json();
  assert.ok(openapi.paths["/v1/fuel/reverse-engineer"]);

  const skillMd = await skillRes.text();
  assert.match(skillMd, /\/v1\/fuel\/reverse-engineer/);

  const llmsTxt = await llmsRes.text();
  assert.match(llmsTxt, /\/v1\/fuel\/reverse-engineer/);

  const card = await cardRes.json();
  assert.ok(card.capabilities.includes("reverse_engineer"));
});

test("POST /v1/pass/prepay enforces 402/503 fail-closed and mints 30-day af402_live pass usable on /v1/fuel/* and /mcp", async () => {
  const PASS_TEST_SECRET = "test-pass-signing-secret-0123456789abcdef";
  const PASS_ENV = { ...ENV, KUROX_SIGNING_SECRET: PASS_TEST_SECRET };
  const getRes = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/v1/pass/prepay", { method: "GET" }),
    ENV,
  );
  assert.equal(getRes.status, 405);

  // 1. Unpaid request returns x402 V2 402 challenge for $5.00 USDC (5000000 atomic units) on Base + Solana
  const unpaidRes = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/v1/pass/prepay", { method: "POST" }),
    ENV,
  );
  assert.equal(unpaidRes.status, 402);
  const reqHeader = unpaidRes.headers.get("PAYMENT-REQUIRED");
  assert.ok(reqHeader, "Expected PAYMENT-REQUIRED header on 402 /v1/pass/prepay");
  const challenge = JSON.parse(Buffer.from(reqHeader, "base64").toString("utf8"));
  assert.equal(challenge.x402Version, 2);

  const baseOpt = challenge.accepts.find((a) => a.network === "eip155:8453");
  const solOpt = challenge.accepts.find((a) => a.network === "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp");
  assert.ok(baseOpt && solOpt, "Expected both Base and Solana accept options");
  assert.equal(baseOpt.amount, "5000000");
  assert.equal(baseOpt.payTo, "0x80E0Ae84679b7f11bE171DaADd492FBECf628cd6");
  assert.equal(solOpt.amount, "5000000");
  assert.equal(solOpt.payTo, "9wuMysgXwNhtQeqJgGByAiMYc4EjzZ5wUSmnjrrt3ffh");
  assert.equal(solOpt.extra?.recipientAta, "DD3A7jaXFeHcif9eYj6Vhomuxypat5Yxi8ow6wxz27yL");

  const mkPaidSig = (acceptedOpt, valueStr) =>
    Buffer.from(
      JSON.stringify({
        x402Version: 2,
        resource: challenge.resource,
        accepted: acceptedOpt,
        payload: {
          signature: `0x${"11".repeat(65)}`,
          authorization: {
            from: "0x1111111111111111111111111111111111111111",
            to: acceptedOpt.payTo,
            value: valueStr,
            validAfter: "0",
            validBefore: "9999999999",
            nonce: `0x${"22".repeat(32)}`,
          },
        },
      }),
    ).toString("base64");

  const origFetch = globalThis.fetch;
  let verifyCalls = 0;
  let settleCalls = 0;
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u === "https://facilitator.payai.network/verify") {
      verifyCalls += 1;
      return new Response(JSON.stringify({ isValid: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    if (u === "https://facilitator.payai.network/settle") {
      settleCalls += 1;
      return new Response(
        JSON.stringify({
          success: true,
          payer: "0x1111111111111111111111111111111111111111",
          transaction: "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u.startsWith("https://pypi.org/pypi/fastapi/json")) {
      return new Response(
        JSON.stringify({
          info: {
            version: "0.115.0",
            summary: "FastAPI framework",
            requires_python: ">=3.8",
            license: "MIT",
            author: "Tiangolo",
            requires_dist: ["starlette>=0.40.0", "pydantic>=2.0"],
            project_urls: { Homepage: "https://fastapi.tiangolo.com/" },
          },
          releases: { "0.115.0": [{ upload_time: "2026-10-01T00:00:00Z" }] },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    throw new Error(`Unexpected fetch in prepay test: ${u}`);
  };

  try {
    // 2. Fail closed with 503 BEFORE PayAI /verify or /settle when KUROX_SIGNING_SECRET is missing
    const noSecretPrepay = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/pass/prepay", {
        method: "POST",
        headers: { "PAYMENT-SIGNATURE": mkPaidSig(baseOpt, "5000000") },
      }),
      ENV,
    );
    assert.equal(noSecretPrepay.status, 503);
    const noSecretBody = await noSecretPrepay.json();
    assert.equal(noSecretBody.error, "signing_secret_not_configured");
    assert.equal(noSecretBody.charged, false);
    assert.equal(verifyCalls, 0);
    assert.equal(settleCalls, 0);

    // 3. Reject underpaid x402 payload (e.g. $0.01 instead of $5.00) with 402 without calling PayAI
    const underpaidRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/pass/prepay", {
        method: "POST",
        headers: { "PAYMENT-SIGNATURE": mkPaidSig({ ...baseOpt, amount: "10000" }, "10000") },
      }),
      PASS_ENV,
    );
    assert.equal(underpaidRes.status, 402);
    assert.equal(verifyCalls, 0);
    assert.equal(settleCalls, 0);

    // 4. Valid $5.00 settlement mints 30-day af402_live_... pass + PAYMENT-RESPONSE header
    const mintRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/pass/prepay", {
        method: "POST",
        headers: { "PAYMENT-SIGNATURE": mkPaidSig(baseOpt, "5000000") },
      }),
      PASS_ENV,
    );
    assert.equal(mintRes.status, 200);
    assert.equal(verifyCalls, 1);
    assert.equal(settleCalls, 1);
    const mintBody = await mintRes.json();
    assert.equal(mintBody.status, "active");
    assert.match(mintBody.api_key, /^af402_live_\d+_[A-Za-z0-9]+\.[0-9a-f]{64}$/);
    const payRespHdr = mintRes.headers.get("PAYMENT-RESPONSE");
    assert.ok(payRespHdr, "Expected PAYMENT-RESPONSE header on 200 /v1/pass/prepay");
    const payResp = JSON.parse(Buffer.from(payRespHdr, "base64").toString("utf8"));
    assert.equal(payResp.success, true);
    assert.equal(payResp.transaction, "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890");

    // 5. Issued af402_live_... token works via Authorization: Bearer AND X-API-Key on /v1/fuel/* and /mcp
    const bearerFuel = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=fastapi&ecosystem=pypi", {
        headers: { Authorization: `Bearer ${mintBody.api_key}` },
      }),
      PASS_ENV,
    );
    assert.equal(bearerFuel.status, 200);
    assert.equal(bearerFuel.headers.get("X-Kurox-Auth"), "bearer-api-key");

    const xApiFuel = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=fastapi&ecosystem=pypi", {
        headers: { "X-API-Key": mintBody.api_key },
      }),
      PASS_ENV,
    );
    assert.equal(xApiFuel.status, 200);

    const mcpPassRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/mcp", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${mintBody.api_key}`,
        },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 77,
          method: "tools/call",
          params: { name: "fuel_sdk_spec", arguments: { package: "fastapi", ecosystem: "pypi" } },
        }),
      }),
      PASS_ENV,
    );
    assert.equal(mcpPassRes.status, 200);
    const mcpPassBody = await mcpPassRes.json();
    assert.equal(mcpPassBody.result.isError, false);
    assert.equal(mcpPassBody.result._meta["kurox/auth"].mode, "bearer-api-key");
    assert.equal(mcpPassBody.result._meta["kurox/auth"].tier, "agency_pass_30d");

    // 6. Tampered, malformed, and expired af402_live tokens fail closed with 401 on /v1/fuel/* and /mcp
    const tamperedChar = mintBody.api_key.endsWith("0") ? "1" : "0";
    const tamperedPass = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=fastapi", {
        headers: { Authorization: `Bearer ${mintBody.api_key.slice(0, -1)}${tamperedChar}` },
      }),
      PASS_ENV,
    );
    assert.equal(tamperedPass.status, 401);

    const malformedMcp = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/mcp", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": "af402_live_badformat" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 78,
          method: "tools/call",
          params: { name: "fuel_sdk_spec", arguments: { package: "fastapi" } },
        }),
      }),
      PASS_ENV,
    );
    assert.equal(malformedMcp.status, 401);

    const cryptoNode = await import("node:crypto");
    const expiredCore = "af402_live_1000000000_0xabcdef1234";
    const expiredHmac = cryptoNode.createHmac("sha256", PASS_TEST_SECRET).update(expiredCore).digest("hex");
    const expiredPass = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=fastapi", {
        headers: { Authorization: `Bearer ${expiredCore}.${expiredHmac}` },
      }),
      PASS_ENV,
    );
    assert.equal(expiredPass.status, 401);
  } finally {
    globalThis.fetch = origFetch;
  }
});

test("unpaid /v1/fuel/b2b-intent-leads ignores disabled X-Fuel-Session and returns 402 dual-chain challenge", async () => {
  const res = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/b2b-intent-leads", {
      headers: { "X-Fuel-Session": "fuel_pass_stale" },
    }),
    ENV,
  );
  assert.equal(res.status, 402);
  const challengeHdr = res.headers.get("PAYMENT-REQUIRED");
  assert.ok(challengeHdr);
  const decoded = JSON.parse(Buffer.from(challengeHdr, "base64").toString("utf8"));
  assert.equal(decoded.x402Version, 2);
  const networks = decoded.accepts.map((a) => a.network);
  assert.ok(networks.includes("eip155:8453"));
  assert.ok(networks.includes("solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"));
});

test("preview routes fail cleanly with 502 and zero synthetic fallback data when upstreams return empty/error", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ hits: [] }), { status: 200 });
  try {
    const leadsRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/preview/leads"),
      ENV,
    );
    assert.equal(leadsRes.status, 502);
    const leadsBody = await leadsRes.json();
    assert.equal(leadsBody.charged, false);
    assert.doesNotMatch(JSON.stringify(leadsBody), /VectorFlow|PrismRelay/i);

    globalThis.fetch = async () => new Response("Service Unavailable", { status: 503 });
    const mdRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/preview/llm-clean-markdown"),
      ENV,
    );
    assert.equal(mdRes.status, 502);
    const mdBody = await mdRes.json();
    assert.equal(mdBody.charged, false);
    assert.doesNotMatch(JSON.stringify(mdBody), /VectorFlow/i);
  } finally {
    globalThis.fetch = ORIG_FETCH;
  }
});

test("/v1/preview/ecom-price-stock parses live Schema.org JSON-LD without mock Wireless Charging Dock", async () => {
  globalThis.fetch = async () =>
    new Response(
      `<html><head><script type="application/ld+json">${JSON.stringify({
        "@context": "https://schema.org/",
        "@graph": [
          {
            "@type": "Product",
            name: "Bulbasaur",
            sku: "4391",
            offers: { price: "63.00", priceCurrency: "GBP", availability: "https://schema.org/InStock" },
          },
        ],
      })}</script></head><body></body></html>`,
      { status: 200, headers: { "content-type": "text/html" } },
    );
  try {
    const res = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/preview/ecom-price-stock"),
      ENV,
    );
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.title, "Bulbasaur");
    assert.equal(body.price, 63);
    assert.equal(body.currency, "GBP");
    assert.equal(body.sku, "4391");
    assert.doesNotMatch(JSON.stringify(body), /Wireless Charging Dock|PREVIEW-SKU-1|example\.com/i);
  } finally {
    globalThis.fetch = ORIG_FETCH;
  }
});

test("MCP initialize and tools/list expose all 5 AgentFuel tools", async () => {
  const res = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/mcp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }),
    }),
    ENV,
  );
  assert.equal(res.status, 200);
  const rpc = await res.json();
  assert.equal(rpc.result.tools.length, 5);
  assert.ok(rpc.result.tools.some((t) => t.name === "fuel_reverse_engineer"));
});

test("Stripe Checkout creation, instant ZIP download fulfillment, Bearer API key auth & webhook signature verification", async () => {
  const TEST_SECRET = "test_signing_secret_32_bytes_minimum_ok_12345";
  const TEST_WEBHOOK_SECRET = "whsec_test_secret_12345";
  const STRIPE_ENV = {
    ...ENV,
    STRIPE_SECRET_KEY: "sk_test_mock_key",
    KUROX_SIGNING_SECRET: TEST_SECRET,
    STRIPE_WEBHOOK_SECRET: TEST_WEBHOOK_SECRET,
  };

  // 1. Invalid plan / sku fail closed cleanly with 400
  const badPlanRes = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/v1/checkout/api-key?plan=unknown"),
    STRIPE_ENV,
  );
  assert.equal(badPlanRes.status, 400);

  const badSkuRes = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/v1/checkout/bundle?sku=nonexistent"),
    STRIPE_ENV,
  );
  assert.equal(badSkuRes.status, 400);

  // 2. Checkout creation (303 redirect & format=json) + Fulfillment (/v1/stripe/success + /v1/stripe/download)
  let capturedFormBodies = [];
  globalThis.fetch = async (url, init = {}) => {
    const u = String(url);
    if (u === "https://api.stripe.com/v1/checkout/sessions" && init.method === "POST") {
      capturedFormBodies.push(String(init.body || ""));
      return new Response(
        JSON.stringify({ id: "cs_test_a1b2c3d4", url: "https://checkout.stripe.com/c/pay/cs_test_a1b2c3d4" }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u.startsWith("https://api.stripe.com/v1/checkout/sessions/cs_test_paid_dual")) {
      return new Response(
        JSON.stringify({
          id: "cs_test_paid_dual",
          payment_status: "paid",
          amount_total: 1500,
          currency: "usd",
          customer_details: { email: "buyer@example.com" },
          metadata: { kind: "bundle", sku: "kurox-security-suite-bundle-v1" },
          line_items: { data: [{ price: { id: "price_1Uc5uGDmOa2iw8hhUDSzdTQc" } }] },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u.startsWith("https://api.stripe.com/v1/checkout/sessions/cs_test_unpaid")) {
      return new Response(
        JSON.stringify({ id: "cs_test_unpaid", payment_status: "unpaid" }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u.startsWith("https://pypi.org/pypi/fastapi/json")) {
      return new Response(
        JSON.stringify({
          info: {
            version: "0.115.0",
            summary: "FastAPI framework",
            requires_python: ">=3.8",
            license: "MIT",
            author: "Tiangolo",
            requires_dist: ["starlette>=0.40.0", "pydantic>=2.0"],
            project_urls: { Homepage: "https://fastapi.tiangolo.com/" },
          },
          releases: { "0.115.0": [{ upload_time: "2025-10-01T00:00:00Z" }] },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    throw new Error(`Unexpected fetch: ${u}`);
  };

  try {
    // 2a. API Key Checkout (303 redirect)
    const redirectRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/checkout/api-key?plan=starter"),
      STRIPE_ENV,
    );
    assert.equal(redirectRes.status, 303);
    assert.equal(redirectRes.headers.get("Location"), "https://checkout.stripe.com/c/pay/cs_test_a1b2c3d4");
    assert.match(capturedFormBodies[0], /unit_amount%5D=500/);

    // 2b. Bundle Checkout (JSON)
    const bundleJsonRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/checkout/bundle?sku=dual&format=json"),
      STRIPE_ENV,
    );
    assert.equal(bundleJsonRes.status, 200);
    const bundleJson = await bundleJsonRes.json();
    assert.equal(bundleJson.id, "cs_test_a1b2c3d4");
    assert.match(capturedFormBodies[1], /price_1Uc5uGDmOa2iw8hhUDSzdTQc/);

    // 2c. Unpaid session rejects with 402
    const unpaidRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/stripe/success?session_id=cs_test_unpaid&format=json"),
      STRIPE_ENV,
    );
    assert.equal(unpaidRes.status, 402);

    // 2d. Paid session mints working API key + 2 download ZIP URLs
    const successRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/stripe/success?session_id=cs_test_paid_dual&format=json"),
      STRIPE_ENV,
    );
    assert.equal(successRes.status, 200);
    const fulfillment = await successRes.json();
    assert.equal(fulfillment.paid, true);
    assert.ok(fulfillment.api_key.startsWith("sk_kurox_v1."));
    assert.equal(fulfillment.downloads.length, 2);

    // 2e. Download actual CanaryGuard + RugShield ZIP bytes via signed token
    const dl1 = await worker.fetch(new Request(fulfillment.downloads[0].url), STRIPE_ENV);
    assert.equal(dl1.status, 200);
    assert.equal(dl1.headers.get("Content-Type"), "application/zip");
    const zip1Buf = new Uint8Array(await dl1.arrayBuffer());
    assert.equal(zip1Buf.byteLength, 41842);
    assert.equal(zip1Buf[0], 0x50); // 'P'
    assert.equal(zip1Buf[1], 0x4b); // 'K'

    const dl2 = await worker.fetch(new Request(fulfillment.downloads[1].url), STRIPE_ENV);
    assert.equal(dl2.status, 200);
    const zip2Buf = new Uint8Array(await dl2.arrayBuffer());
    assert.equal(zip2Buf.byteLength, 42358);
    assert.equal(zip2Buf[0], 0x50);
    assert.equal(zip2Buf[1], 0x4b);

    // 2f. Tampered / missing download tokens fail closed
    const badDl = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/stripe/download?token=dl_v1.tampered.sig"),
      STRIPE_ENV,
    );
    assert.equal(badDl.status, 403);
    const missingDl = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/stripe/download"),
      STRIPE_ENV,
    );
    assert.equal(missingDl.status, 400);

    // 3. Bearer API key authenticates both HTTP /v1/fuel/* and MCP tools/call without x402
    const httpFuelRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=fastapi&ecosystem=pypi", {
        headers: { Authorization: `Bearer ${fulfillment.api_key}` },
      }),
      STRIPE_ENV,
    );
    assert.equal(httpFuelRes.status, 200);
    assert.equal(httpFuelRes.headers.get("X-Kurox-Auth"), "bearer-api-key");
    const httpFuelBody = await httpFuelRes.json();
    assert.equal(httpFuelBody.package, "fastapi");

    const mcpFuelRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/mcp", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": fulfillment.api_key,
        },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 99,
          method: "tools/call",
          params: { name: "fuel_sdk_spec", arguments: { package: "fastapi", ecosystem: "pypi" } },
        }),
      }),
      STRIPE_ENV,
    );
    assert.equal(mcpFuelRes.status, 200);
    const mcpFuelBody = await mcpFuelRes.json();
    assert.equal(mcpFuelBody.result.isError, false);
    assert.equal(mcpFuelBody.result._meta["kurox/auth"].mode, "bearer-api-key");

    // 4. Tampered & expired Bearer keys fail closed (401), missing secret fails closed (503)
    const tamperedHttpRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=fastapi", {
        headers: { Authorization: `${`Bearer ${fulfillment.api_key}`}tamper` },
      }),
      STRIPE_ENV,
    );
    assert.equal(tamperedHttpRes.status, 401);

    const expiredKey = await signKuroxToken(
      { typ: "api_key", sid: "cs_exp", sku: "kurox-api-starter-30d", tier: "starter", iat: 100, exp: 200 },
      TEST_SECRET,
      "sk_kurox_v1",
    );
    const expiredMcpRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/mcp", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${expiredKey}` },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 100,
          method: "tools/call",
          params: { name: "fuel_sdk_spec", arguments: { package: "fastapi" } },
        }),
      }),
      STRIPE_ENV,
    );
    assert.equal(expiredMcpRes.status, 401);

    const noSecretRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=fastapi", {
        headers: { Authorization: `Bearer ${fulfillment.api_key}` },
      }),
      ENV,
    );
    assert.equal(noSecretRes.status, 503);

    // 5. Stripe Webhook HMAC-SHA256 Verification
    const whBody = JSON.stringify({ id: "evt_1", type: "checkout.session.completed" });
    const ts = Math.floor(Date.now() / 1000);
    const cryptoNode = await import("node:crypto");
    const sigHex = cryptoNode.createHmac("sha256", TEST_WEBHOOK_SECRET).update(`${ts}.${whBody}`).digest("hex");

    const goodWh = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/stripe/webhook", {
        method: "POST",
        headers: { "Stripe-Signature": `t=${ts},v1=${sigHex}` },
        body: whBody,
      }),
      STRIPE_ENV,
    );
    assert.equal(goodWh.status, 200);
    const goodWhJson = await goodWh.json();
    assert.equal(goodWhJson.received, true);

    const badWh = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/stripe/webhook", {
        method: "POST",
        headers: { "Stripe-Signature": `t=${ts},v1=${"0".repeat(64)}` },
        body: whBody,
      }),
      STRIPE_ENV,
    );
    assert.equal(badWh.status, 400);
  } finally {
    globalThis.fetch = ORIG_FETCH;
  }
});

test("SVG Safety Badge, $19 Live CSV Pack checkout/download & RapidAPI bypass work cleanly", async () => {
  const TEST_SECRET = "test_signing_secret_32_bytes_minimum_ok_12345";
  const TEST_ENV = {
    ...ENV,
    STRIPE_SECRET_KEY: "sk_test_mock_key",
    KUROX_SIGNING_SECRET: TEST_SECRET,
    RAPIDAPI_PROXY_SECRET: "rapid_secret_xyz",
  };

  globalThis.fetch = async (url, init = {}) => {
    const u = String(url);
    if (u === "https://api.stripe.com/v1/checkout/sessions" && init.method === "POST") {
      assert.match(String(init.body || ""), /unit_amount%5D=1900/);
      assert.match(String(init.body || ""), /kind%5D=data_pack/);
      return new Response(
        JSON.stringify({ id: "cs_test_csv_1", url: "https://checkout.stripe.com/c/pay/cs_test_csv_1" }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u.startsWith("https://api.stripe.com/v1/checkout/sessions/cs_test_paid_csv")) {
      return new Response(
        JSON.stringify({
          id: "cs_test_paid_csv",
          payment_status: "paid",
          amount_total: 1900,
          currency: "usd",
          customer_details: { email: "agency@example.com" },
          metadata: { kind: "data_pack", sku: "b2b-tech-intent-leads-csv-v1" },
          line_items: { data: [] },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u.startsWith("https://hn.algolia.com/")) {
      return new Response(
        JSON.stringify({
          hits: [{
            objectID: "42",
            title: "Show HN: Acme, Inc. — Fast Agent Gateway",
            url: "https://acme.example.com",
            author: "founder1",
            points: 55,
            num_comments: 12,
            story_text: "Hiring AI engineers using Next.js and Python"
          }]
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u.startsWith("https://pypi.org/pypi/fastapi/json")) {
      return new Response(
        JSON.stringify({ info: { version: "0.115.0", summary: "FastAPI" }, releases: { "0.115.0": [] } }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u === "https://example.org/safe") {
      return new Response("<html><title>Clean Page</title><body><p>Hello safe world</p></body></html>", {
        status: 200,
        headers: { "content-type": "text/html" },
      });
    }
    throw new Error(`Unexpected fetch: ${u}`);
  };

  try {
    // 1. Live SVG Badge renders cleanly & XML-escapes XSS characters
    const badgeRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/badge/safety?target=https%3A%2F%2Fexample.org%2Fsafe&label=%3Cbad%3E"),
      TEST_ENV,
    );
    assert.equal(badgeRes.status, 200);
    assert.match(badgeRes.headers.get("Content-Type"), /image\/svg\+xml/i);
    const svg = await badgeRes.text();
    assert.match(svg, /<svg /);
    assert.doesNotMatch(svg, /<bad>/);
    assert.match(svg, /&lt;bad&gt;/);

    // 2. CSV Data Pack checkout + fulfillment + RFC-4180 CSV download
    const coRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/checkout/bundle?sku=csv-pack&format=json"),
      TEST_ENV,
    );
    assert.equal(coRes.status, 200);
    const succRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/stripe/success?session_id=cs_test_paid_csv&format=json"),
      TEST_ENV,
    );
    assert.equal(succRes.status, 200);
    const ful = await succRes.json();
    assert.equal(ful.downloads.length, 1);
    assert.match(ful.downloads[0].filename, /\.csv$/);

    const csvRes = await worker.fetch(new Request(ful.downloads[0].url), TEST_ENV);
    assert.equal(csvRes.status, 200);
    assert.match(csvRes.headers.get("Content-Type"), /text\/csv/);
    const csvText = await csvRes.text();
    assert.match(csvText, /^company_name,launch_headline,domain/);
    assert.match(csvText, /"Acme, Inc\.","Acme, Inc\. — Fast Agent Gateway",acme\.example\.com/);
    assert.match(csvText, /AI\/LLM \| Next\.js\/React \| Python,true,100,Early Stage \/ Pre-Seed/);

    // 3. RapidAPI proxy secret bypasses 402 cleanly when matching, fails closed when spoofed
    const rapidOk = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=fastapi&ecosystem=pypi", {
        headers: { "X-RapidAPI-Proxy-Secret": "rapid_secret_xyz" },
      }),
      TEST_ENV,
    );
    assert.equal(rapidOk.status, 200);
    assert.equal(rapidOk.headers.get("X-RapidAPI-Bypass"), "active");

    const rapidBad = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=fastapi&ecosystem=pypi", {
        headers: { "X-RapidAPI-Proxy-Secret": "wrong_secret" },
      }),
      TEST_ENV,
    );
    assert.equal(rapidBad.status, 402);
  } finally {
    globalThis.fetch = ORIG_FETCH;
  }
});

test("Intelligence Store (/store, /v1/store/products, Stripe & x402 checkout, downloads, Security Audit & SVG badge)", async () => {
  const STORE_SECRET = "store-signing-secret-0123456789abcdef";
  const STORE_ENV = { ...ENV, STRIPE_SECRET_KEY: "sk_test_store_123", KUROX_SIGNING_SECRET: STORE_SECRET };

  // 1. Storefront HTML, JSON Catalog & Previews
  const [storeHtmlRes, productsRes, previewRes] = await Promise.all([
    worker.fetch(new Request("https://agentfuel402.ak10082247.workers.dev/store"), STORE_ENV),
    worker.fetch(new Request("https://agentfuel402.ak10082247.workers.dev/v1/store/products"), STORE_ENV),
    worker.fetch(new Request("https://agentfuel402.ak10082247.workers.dev/v1/store/preview?sku=base-alpha-feed"), STORE_ENV),
  ]);
  assert.equal(storeHtmlRes.status, 200);
  assert.match(storeHtmlRes.headers.get("Content-Type"), /text\/html/i);
  const storeHtml = await storeHtmlRes.text();
  assert.match(storeHtml, /AgentFuel402 Intelligence Store/);
  assert.match(storeHtml, /base-alpha-feed/);
  assert.match(storeHtml, /b2b-startup-leads-500/);
  assert.match(storeHtml, /instant-security-audit/);

  assert.equal(productsRes.status, 200);
  const catalog = await productsRes.json();
  assert.equal(catalog.products.length, 3);
  const byId = Object.fromEntries(catalog.products.map((p) => [p.id, p]));
  assert.equal(byId["base-alpha-feed"].amount_cents, 2900);
  assert.equal(byId["base-alpha-feed"].amount_micro_usdc, "29000000");
  assert.equal(byId["b2b-startup-leads-500"].amount_cents, 3900);
  assert.equal(byId["b2b-startup-leads-500"].amount_micro_usdc, "39000000");
  assert.equal(byId["instant-security-audit"].amount_cents, 999);
  assert.equal(byId["instant-security-audit"].amount_micro_usdc, "9990000");
  assert.ok(byId["base-alpha-feed"].live_stats.total_tokens >= 10);
  assert.ok(byId["b2b-startup-leads-500"].live_stats.total_leads >= 100);

  assert.equal(previewRes.status, 200);
  const preview = await previewRes.json();
  assert.equal(preview.preview, true);
  assert.equal(preview.sample_rows.length, 2);

  // 2. Audit target validation BEFORE payment
  const badAudit400 = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/v1/store/buy?sku=instant-security-audit", { method: "POST" }),
    STORE_ENV,
  );
  assert.equal(badAudit400.status, 400);

  // 3. Unpaid x402 challenges for all 3 SKUs
  const cAlpha = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/v1/store/buy?sku=base-alpha-feed", { method: "POST" }),
    STORE_ENV,
  );
  assert.equal(cAlpha.status, 402);
  const cAlphaJson = JSON.parse(Buffer.from(cAlpha.headers.get("PAYMENT-REQUIRED"), "base64").toString("utf8"));
  assert.equal(cAlphaJson.accepts[0].amount, "29000000");

  const cAudit = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/v1/store/buy?sku=instant-security-audit&target=acme/mcp-server", { method: "POST" }),
    STORE_ENV,
  );
  assert.equal(cAudit.status, 402);
  const cAuditJson = JSON.parse(Buffer.from(cAudit.headers.get("PAYMENT-REQUIRED"), "base64").toString("utf8"));
  assert.equal(cAuditJson.accepts[0].amount, "9990000");

  const origFetch = globalThis.fetch;
  let verifyCalls = 0;
  let settleCalls = 0;
  globalThis.fetch = async (url, init) => {
    const u = String(url);
    if (u === "https://api.stripe.com/v1/checkout/sessions") {
      return new Response(
        JSON.stringify({ id: "cs_test_store_alpha", url: "https://checkout.stripe.com/c/pay/cs_test_store_alpha" }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u.startsWith("https://api.stripe.com/v1/checkout/sessions/cs_test_paid_store_alpha")) {
      return new Response(
        JSON.stringify({
          id: "cs_test_paid_store_alpha",
          payment_status: "paid",
          amount_total: 2900,
          currency: "usd",
          customer_details: { email: "quant@example.com" },
          metadata: { kind: "store_product", sku: "store-base-alpha-feed-v1", product_id: "base-alpha-feed", file_format: "csv" },
          line_items: { data: [] },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u === "https://facilitator.payai.network/verify") {
      verifyCalls += 1;
      return new Response(JSON.stringify({ isValid: true }), { status: 200, headers: { "content-type": "application/json" } });
    }
    if (u === "https://facilitator.payai.network/settle") {
      settleCalls += 1;
      return new Response(
        JSON.stringify({ success: true, payer: "0x2222222222222222222222222222222222222222", transaction: "0xdeadbeef1234567890abcdef" }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u === "https://api.github.com/repos/missing/notfound") {
      return new Response(JSON.stringify({ message: "Not Found" }), { status: 404, headers: { "content-type": "application/json" } });
    }
    if (u === "https://api.github.com/repos/acme/mcp-server") {
      return new Response(
        JSON.stringify({ html_url: "https://github.com/acme/mcp-server", default_branch: "main", stargazers_count: 180, language: "TypeScript", archived: false, license: { spdx_id: "MIT" }, open_issues_count: 2 }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u === "https://api.github.com/repos/acme/mcp-server/contents") {
      return new Response(
        JSON.stringify([{ name: "README.md" }, { name: "package.json" }, { name: "LICENSE" }, { name: "server.json" }]),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (u.startsWith("https://raw.githubusercontent.com/acme/mcp-server/main/package.json")) {
      return new Response(JSON.stringify({ name: "mcp-server", dependencies: { zod: "^3.23.0" } }), { status: 200, headers: { "content-type": "application/json" } });
    }
    if (u.startsWith("https://raw.githubusercontent.com/acme/mcp-server/main/README.md")) {
      return new Response("# Safe MCP Server\nClean production documentation.\n", { status: 200, headers: { "content-type": "text/plain" } });
    }
    throw new Error(`Unexpected fetch in store test: ${u}`);
  };

  try {
    // 4. Stripe Store Checkout -> Fulfillment -> /v1/store/download?token=...
    const stripeCoRedirect = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/store/checkout?sku=base-alpha-feed&format=csv"),
      STORE_ENV,
    );
    assert.equal(stripeCoRedirect.status, 303);
    assert.equal(stripeCoRedirect.headers.get("Location"), "https://checkout.stripe.com/c/pay/cs_test_store_alpha");

    const stripeSucc = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/stripe/success?session_id=cs_test_paid_store_alpha&format=json"),
      STORE_ENV,
    );
    assert.equal(stripeSucc.status, 200);
    const fulData = await stripeSucc.json();
    assert.equal(fulData.sku, "store-base-alpha-feed-v1");
    assert.equal(fulData.downloads.length, 2);
    assert.match(fulData.downloads[0].url, /\/v1\/store\/download\?token=/);

    const alphaCsvRes = await worker.fetch(new Request(fulData.downloads[0].url), STORE_ENV);
    assert.equal(alphaCsvRes.status, 200);
    assert.match(alphaCsvRes.headers.get("Content-Type"), /text\/csv/);
    const alphaCsv = await alphaCsvRes.text();
    assert.match(alphaCsv, /^chain,symbol,token_address/);

    const alphaJsonRes = await worker.fetch(new Request(fulData.downloads[1].url), STORE_ENV);
    assert.equal(alphaJsonRes.status, 200);
    const alphaJson = await alphaJsonRes.json();
    assert.equal(alphaJson.product, "base-alpha-feed");
    assert.ok(alphaJson.tokens.length >= 10);

    // 5. x402 Crypto Purchase ($9.99 Instant Audit): 404 target rejects BEFORE settlement (charged: false)
    const auditOpt = cAuditJson.accepts[0];
    const mkSig = (opt, amt) =>
      Buffer.from(
        JSON.stringify({
          x402Version: 2,
          resource: cAuditJson.resource,
          accepted: opt,
          payload: { signature: `0x${"33".repeat(65)}`, authorization: { from: "0x2222", to: opt.payTo, value: amt, validAfter: "0", validBefore: "9999999999", nonce: `0x${"44".repeat(32)}` } },
        }),
      ).toString("base64");

    const auditMissingRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/store/buy?sku=instant-security-audit&target=missing/notfound", {
        method: "POST",
        headers: { "PAYMENT-SIGNATURE": mkSig(auditOpt, "9990000") },
      }),
      STORE_ENV,
    );
    assert.equal(auditMissingRes.status, 404);
    const auditMissingBody = await auditMissingRes.json();
    assert.equal(auditMissingBody.charged, false);
    assert.equal(settleCalls, 0);

    // 6. Paid $9.99 Audit settles on-chain -> JSON + Printable HTML Certificate + Verified SVG Badge
    const auditPaidRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/store/buy?sku=instant-security-audit&target=https://github.com/acme/mcp-server", {
        method: "POST",
        headers: { "PAYMENT-SIGNATURE": mkSig(auditOpt, "9990000") },
      }),
      STORE_ENV,
    );
    assert.equal(auditPaidRes.status, 200);
    assert.equal(verifyCalls, 2);
    assert.equal(settleCalls, 1);
    const auditBody = await auditPaidRes.json();
    assert.equal(auditBody.paid, true);
    assert.equal(auditBody.deliverable.target, "acme/mcp-server");
    assert.equal(auditBody.deliverable.score, 90); // 100 - 10 missing SECURITY.md
    assert.equal(auditBody.deliverable.grade, "A");
    assert.ok(auditBody.deliverable.certificate_signature);

    const htmlCertRes = await worker.fetch(new Request(auditBody.downloads[1].url), STORE_ENV);
    assert.equal(htmlCertRes.status, 200);
    assert.match(htmlCertRes.headers.get("Content-Type"), /text\/html/);
    assert.match(await htmlCertRes.text(), /Print \/ Save PDF Certificate/);

    const svgBadgeRes = await worker.fetch(new Request(auditBody.deliverable.readme_badge_url), STORE_ENV);
    assert.equal(svgBadgeRes.status, 200);
    assert.match(svgBadgeRes.headers.get("Content-Type"), /image\/svg\+xml/);
    assert.match(await svgBadgeRes.text(), /acme\/mcp-server/);

    const badgeUrlStr = auditBody.deliverable.readme_badge_url;
    const lastHex = badgeUrlStr.slice(-1) === "0" ? "1" : "0";
    const badBadge = await worker.fetch(
      new Request(`${badgeUrlStr.slice(0, -1)}${lastHex}`),
      STORE_ENV,
    );
    assert.equal(badBadge.status, 403);
  } finally {
    globalThis.fetch = ORIG_FETCH;
  }
});

test("Stripe MPP (method=stripe) challenge, Payment-Receipt, 7-day unified pass, 422 never-charge invariant, /v1/mpp/pass & /internal/mpp/stripe/verify", async () => {
  const { createHmac } = await import("node:crypto");
  const { computeChallengeId, DEFAULT_STRIPE_PROFILE_ID, buildStripeChargeChallenge } = await import("./stripe_mpp.js");
  const MPP_ENV = {
    ...ENV,
    KUROX_SIGNING_SECRET: "kurox_mpp_test_signing_secret_32bytes_min",
    STRIPE_SECRET_KEY: "sk_test_mpp_mock_key_000000000000000",
  };

  try {
    // 1. Unpaid /v1/fuel/b2b-intent-leads emits valid WWW-Authenticate: Payment ..., method="stripe" + X402 dual headers
    const unpaidRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/b2b-intent-leads"),
      MPP_ENV,
    );
    assert.equal(unpaidRes.status, 402);
    const wwwAuth = unpaidRes.headers.get("WWW-Authenticate") || "";
    assert.ok(wwwAuth.startsWith("Payment "), "WWW-Authenticate must start with Payment scheme");
    assert.match(wwwAuth, /method="stripe"/);
    assert.match(wwwAuth, /intent="charge"/);
    assert.match(wwwAuth, /realm="agentfuel402\.ak10082247\.workers\.dev"/);
    const unpaidJson = await unpaidRes.json();
    assert.equal(unpaidJson.mpp.method, "stripe");
    assert.equal(unpaidJson.mpp.amountCents, "50");
    assert.equal(unpaidJson.mpp.challenge.request.methodDetails.networkId, DEFAULT_STRIPE_PROFILE_ID);

    // 2. Malformed Authorization: Payment garbage returns 402 with fresh WWW-Authenticate (never 500 or 401)
    const badCredRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/b2b-intent-leads", {
        headers: { Authorization: "Payment dGhpcyBpcyBnYXJiYWdl" },
      }),
      MPP_ENV,
    );
    assert.equal(badCredRes.status, 402);
    assert.ok((badCredRes.headers.get("WWW-Authenticate") || "").startsWith("Payment "));

    // Build real serialized MPP credential matching mppx@0.21.1 wire format
    const reqParamMatch = /request="([^"]+)"/.exec(wwwAuth);
    assert.ok(reqParamMatch?.[1]);
    const serializeCred = (challengeObj, spt = "spt_test_valid_token_123") => {
      const wire = {
        challenge: {
          id: challengeObj.id,
          realm: challengeObj.realm,
          method: challengeObj.method,
          intent: challengeObj.intent,
          expires: challengeObj.expires,
          request: challengeObj._rawReq || Buffer.from(JSON.stringify(challengeObj.request)).toString("base64url"),
        },
        payload: { spt },
      };
      return `Payment ${Buffer.from(JSON.stringify(wire)).toString("base64url")}`;
    };

    const stripeCalls = [];
    globalThis.fetch = async (url, init = {}) => {
      const u = String(url);
      if (u.startsWith("https://api.stripe.com/v1/payment_intents")) {
        stripeCalls.push({ url: u, headers: init.headers, body: String(init.body || "") });
        return new Response(
          JSON.stringify({ id: `pi_mpp_${stripeCalls.length}`, status: "succeeded" }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (u.startsWith("https://hn.algolia.com/")) {
        return new Response(
          JSON.stringify({
            hits: [
              { title: "Show HN: AgentInfra", url: "https://agentinfra.dev", points: 42, num_comments: 11, created_at: "2026-11-22T12:00:00Z" },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (u.startsWith("https://pypi.org/")) {
        return new Response("Not Found", { status: 404 });
      }
      throw new Error(`Unexpected external fetch in test: ${u}`);
    };

    // 3. Upstream failure (422) NEVER charges Stripe!
    const sdk402 = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=nonexistent_pkg_xyz"),
      MPP_ENV,
    );
    const sdkWww = sdk402.headers.get("WWW-Authenticate") || "";
    const sdkReqB64 = /request="([^"]+)"/.exec(sdkWww)[1];
    const sdkChallenge = {
      id: /id="([^"]+)"/.exec(sdkWww)[1],
      realm: /realm="([^"]+)"/.exec(sdkWww)[1],
      method: "stripe",
      intent: "charge",
      expires: /expires="([^"]+)"/.exec(sdkWww)[1],
      _rawReq: sdkReqB64,
    };
    const sdk422Res = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/sdk-live-spec?package=nonexistent_pkg_xyz", {
        headers: { Authorization: serializeCred(sdkChallenge, "spt_should_not_charge") },
      }),
      MPP_ENV,
    );
    assert.equal(sdk422Res.status, 422);
    assert.equal((await sdk422Res.json()).charged, false);
    assert.equal(stripeCalls.length, 0);

    // 4. Paid Stripe MPP call on /v1/fuel/b2b-intent-leads settles PaymentIntent, returns Payment-Receipt & mints 7d unified Bearer key
    const validCredHdr = serializeCred({
      ...unpaidJson.mpp.challenge,
      _rawReq: reqParamMatch[1],
    }, "spt_test_charge_001");
    const paidRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/b2b-intent-leads", {
        headers: { Authorization: validCredHdr },
      }),
      MPP_ENV,
    );
    assert.equal(paidRes.status, 200);
    assert.equal(stripeCalls.length, 1);
    assert.equal(stripeCalls[0].headers["Stripe-Version"], "2026-07-29.preview");
    assert.match(stripeCalls[0].body, /shared_payment_granted_token=spt_test_charge_001/);
    assert.match(stripeCalls[0].body, /metadata%5Bmachine_payment%5D=true/);
    assert.equal(paidRes.headers.get("X-Kurox-Auth"), "stripe-mpp");
    const receiptHdr = paidRes.headers.get("Payment-Receipt");
    assert.ok(receiptHdr);
    const decodedReceipt = JSON.parse(Buffer.from(receiptHdr, "base64url").toString("utf8"));
    assert.equal(decodedReceipt.method, "stripe");
    assert.equal(decodedReceipt.status, "success");
    assert.equal(decodedReceipt.reference, "pi_mpp_1");

    const mintedPassKey = paidRes.headers.get("X-Kurox-Api-Key");
    assert.ok(mintedPassKey && mintedPassKey.startsWith("sk_kurox_v1."));

    // Reuse minted 7-day Bearer key immediately -> zero extra Stripe charges!
    const followUpRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/b2b-intent-leads", {
        headers: { Authorization: `Bearer ${mintedPassKey}` },
      }),
      MPP_ENV,
    );
    assert.equal(followUpRes.status, 200);
    assert.equal(stripeCalls.length, 1);
    assert.equal(followUpRes.headers.get("X-Kurox-Auth"), "bearer-api-key");

    // 5. Replay protection: duplicate challenge.id is rejected 402 without extra Stripe charge
    const replayRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/fuel/b2b-intent-leads", {
        headers: { Authorization: validCredHdr },
      }),
      MPP_ENV,
    );
    assert.equal(replayRes.status, 402);
    assert.equal(stripeCalls.length, 1);

    // 6. Dedicated /v1/mpp/pass?tier=starter enforces 500c minimum and mints 30d Starter key
    const pass402 = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/mpp/pass?tier=starter", { method: "POST" }),
      MPP_ENV,
    );
    assert.equal(pass402.status, 402);
    const passBody = await pass402.json();
    assert.equal(passBody.mpp.amountCents, "500");

    // Paying 50c challenge against tier=starter (500c) must reject 402
    const ch50 = await buildStripeChargeChallenge({
      realm: "agentfuel402.ak10082247.workers.dev",
      amountCents: 50,
      description: "Underpaid pass",
      secretKey: MPP_ENV.KUROX_SIGNING_SECRET,
    });
    const underpaidRes = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/mpp/pass?tier=starter", {
        method: "POST",
        headers: { Authorization: serializeCred({ ...ch50.challenge, _rawReq: ch50.requestEncoded }, "spt_underpay") },
      }),
      MPP_ENV,
    );
    assert.equal(underpaidRes.status, 402);
    assert.equal(stripeCalls.length, 1);

    const passPaid = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/v1/mpp/pass?tier=starter", {
        method: "POST",
        headers: { Authorization: serializeCred({ ...passBody.mpp.challenge, _rawReq: /request="([^"]+)"/.exec(pass402.headers.get("WWW-Authenticate"))[1] }, "spt_starter_500") },
      }),
      MPP_ENV,
    );
    assert.equal(passPaid.status, 200);
    assert.equal(stripeCalls.length, 2);
    const passJson = await passPaid.json();
    assert.equal(passJson.tier, "starter");
    assert.ok(passJson.api_key.startsWith("sk_kurox_v1."));

    // 7. Internal HMAC relay endpoint for CanaryGuard & RugShield fails closed on invalid auth and settles signed sibling requests
    const unauthRelay = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/internal/mpp/stripe/verify", {
        method: "POST",
        body: JSON.stringify({ service: "canaryguard-402" }),
      }),
      MPP_ENV,
    );
    assert.equal(unauthRelay.status, 401);

    const cgChallenge = await buildStripeChargeChallenge({
      realm: "canaryguard-402.onrender.com",
      amountCents: 50,
      description: "CanaryGuard Sanitize Pass",
      secretKey: MPP_ENV.KUROX_SIGNING_SECRET,
    });
    const cgComputedId = await computeChallengeId(cgChallenge.challenge, MPP_ENV.KUROX_SIGNING_SECRET);
    assert.equal(cgChallenge.challenge.id, cgComputedId);

    const relayBody = JSON.stringify({
      service: "canaryguard-402",
      expectedRealm: "canaryguard-402.onrender.com",
      minAmountCents: 50,
      credential: {
        challenge: {
          ...cgChallenge.challenge,
          request: cgChallenge.requestEncoded,
        },
        payload: { spt: "spt_canaryguard_relay_01" },
      },
    });
    const ts = String(Math.floor(Date.now() / 1000));
    const relaySig = createHmac("sha256", MPP_ENV.KUROX_SIGNING_SECRET)
      .update(`${ts}.canaryguard-402.${relayBody}`)
      .digest("base64url");

    const okRelay = await worker.fetch(
      new Request("https://agentfuel402.ak10082247.workers.dev/internal/mpp/stripe/verify", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Kurox-Internal-Timestamp": ts,
          "X-Kurox-Internal-Service": "canaryguard-402",
          "X-Kurox-Internal-Signature": relaySig,
        },
        body: relayBody,
      }),
      MPP_ENV,
    );
    assert.equal(okRelay.status, 200);
    assert.equal(stripeCalls.length, 3);
    const okRelayJson = await okRelay.json();
    assert.equal(okRelayJson.ok, true);
    assert.equal(okRelayJson.paymentIntentId, "pi_mpp_3");
    assert.ok(okRelayJson.apiKey.startsWith("sk_kurox_v1."));
  } finally {
    globalThis.fetch = ORIG_FETCH;
  }
});
