import asyncio
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mcp_server


class TestAgentFuelMCP(unittest.TestCase):
    def test_initialize_and_tools_list(self):
        init_resp = asyncio.run(
            mcp_server.handle_mcp_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        )
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "agentfuel402")

        list_resp = asyncio.run(
            mcp_server.handle_mcp_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        )
        names = [t["name"] for t in list_resp["result"]["tools"]]
        self.assertEqual(
            names,
            [
                "fuel_b2b_leads",
                "fuel_clean_markdown",
                "fuel_ecom_price_stock",
                "fuel_sdk_spec",
                "fuel_reverse_engineer",
            ],
        )

    def test_notifications_return_none_and_unknown_tool_errors(self):
        notif = asyncio.run(
            mcp_server.handle_mcp_jsonrpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )
        self.assertIsNone(notif)

        unknown = asyncio.run(
            mcp_server.handle_mcp_jsonrpc(
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "missing_tool"}}
            )
        )
        self.assertEqual(unknown["error"]["code"], -32601)

    def test_tool_call_executor_dispatch(self):
        async def fake_exec(name, args):
            return {"ok": True, "tool": name, "args": args}

        resp = asyncio.run(
            mcp_server.handle_mcp_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "fuel_sdk_spec", "arguments": {"package": "fastapi", "ecosystem": "pypi"}},
                },
                executor=fake_exec,
            )
        )
        self.assertFalse(resp["result"]["isError"])
        parsed = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(parsed["tool"], "fuel_sdk_spec")

    def test_stdio_entrypoint_subprocess(self):
        cwd = os.path.dirname(os.path.abspath(__file__))
        stdin_payload = "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            ]
        ) + "\n"
        proc = subprocess.run(
            [sys.executable, "entrypoint.py", "--mcp-stdio"],
            cwd=cwd,
            input=stdin_payload,
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )
        lines = [json.loads(line) for line in proc.stdout.strip().splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["id"], 1)
        self.assertEqual(len(lines[1]["result"]["tools"]), 5)


if __name__ == "__main__":
    unittest.main()
