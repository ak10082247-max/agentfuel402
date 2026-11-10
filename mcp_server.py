"""
Shared MCP JSON-RPC 2.0 handler and stdio runner for AgentFuel402.
Powers both FastAPI /mcp (Docker/Glama introspection) and --mcp-stdio.
"""
import asyncio
import json
import sys
from typing import Any, Awaitable, Callable, Dict, Optional

MCP_TOOLS = [
    {
        "name": "fuel_b2b_leads",
        "description": "Fetches live B2B buying intent signals from Show HN with detected tech stacks, domains, and Intent Scores (30-100). Cost: $0.010 USDC via x402.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter category: all, ai, devtools, saas, fin, ecommerce",
                    "default": "all",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum lead signals to return (1-25)",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "fuel_clean_markdown",
        "description": "Fetches any public URL, strips noise/scripts/ads, sanitizes prompt injections, and returns clean Markdown and token estimates. Cost: $0.005 USDC via x402.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Public URL to fetch and clean"},
                "strip_images": {"type": "boolean", "description": "Strip image markdown tags", "default": False},
            },
            "required": ["url"],
        },
    },
    {
        "name": "fuel_ecom_price_stock",
        "description": "Extracts live price, currency, in-stock status, SKU, and discount delta for Shopify, WooCommerce, and Schema.org product URLs. Cost: $0.005 USDC via x402.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Product URL"}
            },
            "required": ["url"],
        },
    },
    {
        "name": "fuel_sdk_spec",
        "description": "Queries live PyPI or npm registry metadata for latest stable version, license, and dependency count. Cost: $0.005 USDC via x402.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package name on PyPI or npm"},
                "ecosystem": {"type": "string", "enum": ["pypi", "npm"], "default": "pypi"},
            },
            "required": ["package"],
        },
    },
    {
        "name": "fuel_reverse_engineer",
        "description": "Detects frameworks, hidden REST/GraphQL endpoints, hydration state, and generates OpenAPI 3.1 specs for a target URL. Cost: $0.020 USDC via x402.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target webpage URL"}
            },
            "required": ["url"],
        },
    },
]


async def execute_local_tool(name: str, arguments: Dict[str, Any]) -> Any:
    """Dispatches an MCP tool call to the shared FastAPI engine handlers."""
    import app as fastapi_app

    args = arguments or {}
    if name == "fuel_b2b_leads":
        limit = max(1, min(25, int(args.get("limit", 10))))
        category = str(args.get("category", "all"))
        return await fastapi_app.get_b2b_intent_leads(limit=limit, category=category)
    if name == "fuel_clean_markdown":
        url = args.get("url")
        if not url:
            raise ValueError("Missing required 'url' argument.")
        return await fastapi_app.clean_markdown(url=str(url))
    if name == "fuel_ecom_price_stock":
        url = args.get("url")
        if not url:
            raise ValueError("Missing required 'url' argument.")
        return await fastapi_app.ecom_price_stock(url=str(url))
    if name == "fuel_sdk_spec":
        pkg = args.get("package")
        if not pkg:
            raise ValueError("Missing required 'package' argument.")
        eco = str(args.get("ecosystem", "pypi"))
        return await fastapi_app.sdk_live_spec(package=str(pkg), ecosystem=eco)
    if name == "fuel_reverse_engineer":
        url = args.get("url")
        if not url:
            raise ValueError("Missing required 'url' argument.")
        return await fastapi_app.reverse_engineer_endpoint(url=str(url))
    raise KeyError(name)


async def handle_mcp_jsonrpc(
    payload: Dict[str, Any],
    executor: Callable[[str, Dict[str, Any]], Awaitable[Any]] = execute_local_tool,
) -> Optional[Dict[str, Any]]:
    """Handles a single JSON-RPC 2.0 MCP message; returns None for notifications."""
    req_id = payload.get("id")
    method = payload.get("method", "")
    params = payload.get("params") or {}

    if method == "initialize":
        proto = params.get("protocolVersion") or "2024-11-05"
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": proto,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "agentfuel402", "version": "1.0.0"},
            },
        }

    if method.startswith("notifications/") or req_id is None:
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        known_names = {t["name"] for t in MCP_TOOLS}
        if tool_name not in known_names:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"},
            }
        try:
            result = await executor(tool_name, params.get("arguments") or {})
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": detail})}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method '{method}' not found"},
    }


async def run_stdio() -> None:
    """Line-delimited JSON-RPC 2.0 MCP server over stdin/stdout."""
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()
            continue

        resp = await handle_mcp_jsonrpc(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(run_stdio())
