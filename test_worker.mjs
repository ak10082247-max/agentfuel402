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

test("POST /v1/pass/prepay fails closed with 503 and charged:false even with a payment header", async () => {
  const res1 = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/v1/pass/prepay", { method: "POST" }),
    ENV,
  );
  assert.equal(res1.status, 503);
  const body1 = await res1.json();
  assert.equal(body1.error, "agency_pass_disabled");
  assert.equal(body1.charged, false);

  const res2 = await worker.fetch(
    new Request("https://agentfuel402.ak10082247.workers.dev/v1/pass/prepay", {
      method: "POST",
      headers: { "PAYMENT-SIGNATURE": "dummy-header" },
    }),
    ENV,
  );
  assert.equal(res2.status, 503);
  const body2 = await res2.json();
  assert.equal(body2.charged, false);
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
