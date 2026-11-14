import test from "node:test";
import assert from "node:assert/strict";
import worker from "./worker.js";

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
