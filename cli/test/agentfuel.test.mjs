import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import http from "node:http";
import {
  AGENTFUEL_UPGRADE_HINT,
  MCP_TOOLS,
  SERVICE_VERSION,
  executeAgentFuelTool,
} from "../dist/index.js";

function generateEphemeralSolanaJsonKey() {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const x = Buffer.from(publicKey.export({ format: "jwk" }).x, "base64url");
  const d = Buffer.from(privateKey.export({ format: "jwk" }).d, "base64url");
  return Array.from(Buffer.concat([d, x]));
}

async function withMockSolanaRpc(fn) {
  const mintData = Buffer.alloc(82, 0);
  mintData.writeUInt32LE(1, 0);
  mintData[44] = 6;
  mintData[45] = 1;
  const mintB64 = mintData.toString("base64");

  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      const parsed = JSON.parse(body);
      const reply = (msg) => {
        if (msg.method === "getAccountInfo") {
          return {
            jsonrpc: "2.0",
            id: msg.id,
            result: {
              context: { slot: 300000000 },
              value: {
                data: [mintB64, "base64"],
                executable: false,
                lamports: 1000000000,
                owner: "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                rentEpoch: 0,
                space: 82,
              },
            },
          };
        }
        if (msg.method === "getLatestBlockhash") {
          return {
            jsonrpc: "2.0",
            id: msg.id,
            result: {
              context: { slot: 300000000 },
              value: {
                blockhash: "11111111111111111111111111111111",
                lastValidBlockHeight: 300000150,
              },
            },
          };
        }
        return { jsonrpc: "2.0", id: msg.id, error: { code: -32601, message: `Unsupported: ${msg.method}` } };
      };
      const out = Array.isArray(parsed) ? parsed.map(reply) : reply(parsed);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(out));
    });
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  try {
    return await fn(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

test("exposes 5 MCP tools and routes unauthenticated calls to free previews or fail-closed 402", async () => {
  assert.equal(SERVICE_VERSION, "1.0.0");
  assert.equal(MCP_TOOLS.length, 5);
  assert.ok(AGENTFUEL_UPGRADE_HINT.includes("apify.com/kuroxreal"));

  const seen = [];
  const customFetch = async (input) => {
    const url = input instanceof Request ? input.url : String(input);
    seen.push(url);
    if (url.includes("/v1/fuel/reverse-engineer")) {
      return new Response(JSON.stringify({ error: "Payment Required" }), { status: 402 });
    }
    return new Response(JSON.stringify({ status: "success", items: 2 }), { status: 200 });
  };

  const leads = await executeAgentFuelTool("fuel_b2b_leads", { category: "ai", limit: 2 }, { customFetch });
  assert.equal(leads.isError, false);
  assert.equal(leads.payload.x402_payment_mode, "free_preview");
  assert.match(seen[0], /\/v1\/preview\/leads\?category=ai&limit=2$/);

  const rea = await executeAgentFuelTool("fuel_reverse_engineer", { url: "https://example.com" }, { customFetch });
  assert.equal(rea.isError, true);
  assert.equal(rea.payload.error, "PAYMENT_REQUIRED_402");
  assert.match(rea.payload.apify_fiat_actor, /reverse-engineer-anything/);
});

test("auto-signs Solana USDC x402 payments via @x402/svm for paid /v1/fuel/* calls", async () => {
  const solKey = generateEphemeralSolanaJsonKey();
  let capturedSig = null;

  await withMockSolanaRpc(async (rpcUrl) => {
    const customFetch = async (input, init) => {
      const url = input instanceof Request ? input.url : String(input);
      const sig =
        (input instanceof Request ? input.headers.get("payment-signature") : null) ??
        (init?.headers instanceof Headers ? init.headers.get("payment-signature") : null);
      if (!sig) {
        const pr = Buffer.from(
          JSON.stringify({
            x402Version: 2,
            resource: { url, description: "AgentFuel REA", mimeType: "application/json" },
            accepts: [
              {
                scheme: "exact",
                network: "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
                amount: "20000",
                asset: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                payTo: "9wuMysgXwNhtQeqJgGByAiMYc4EjzZ5wUSmnjrrt3ffh",
                maxTimeoutSeconds: 300,
                extra: {
                  name: "USD Coin (Solana)",
                  version: "2",
                  feePayer: "CjNFTjvBhbJJd2B5ePPMHRLx1ELZpa8dwQgGL727eKww",
                },
              },
            ],
          }),
          "utf8",
        ).toString("base64");
        return new Response(JSON.stringify({ error: "Payment Required" }), {
          status: 402,
          headers: { "content-type": "application/json", "payment-required": pr },
        });
      }
      capturedSig = JSON.parse(Buffer.from(sig, "base64").toString("utf8"));
      return new Response(JSON.stringify({ openapi: "3.1.0", discovered_endpoints: [] }), { status: 200 });
    };

    const res = await executeAgentFuelTool(
      "fuel_reverse_engineer",
      { url: "https://example.com" },
      { solanaPrivateKey: solKey, solanaRpcUrl: rpcUrl, customFetch },
    );
    assert.equal(res.isError, false);
    assert.equal(res.payload.x402_payment_mode, "x402_paid");
    assert.equal(capturedSig.accepted.amount, "20000");
    assert.equal(capturedSig.accepted.network, "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp");
    assert.ok(capturedSig.payload.transaction.length > 40);
  });
});
