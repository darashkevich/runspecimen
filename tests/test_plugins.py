"""Plugin adapter and approve-gate coverage for Codex/Cursor/Claude/Grok."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "runspecimen"
ADAPTER = PLUGIN / "scripts" / "runspecimen_adapter.py"
GATE = PLUGIN / "scripts" / "block_approve_gate.py"
MCP = PLUGIN / "scripts" / "runspecimen_mcp.py"


class PluginManifestTests(unittest.TestCase):
    def test_host_manifests_share_version_and_name(self) -> None:
        expected = "0.2.0-rc.10"
        manifests = {
            "codex": PLUGIN / ".codex-plugin" / "plugin.json",
            "cursor": PLUGIN / ".cursor-plugin" / "plugin.json",
            "claude": PLUGIN / ".claude-plugin" / "plugin.json",
        }
        loaded = {key: json.loads(path.read_text(encoding="utf-8")) for key, path in manifests.items()}
        for key, doc in loaded.items():
            self.assertEqual(doc.get("name"), "runspecimen", key)
            version = str(doc.get("version", "")).split("+", 1)[0]
            self.assertEqual(version, expected, key)

    def test_marketplaces_point_at_plugin(self) -> None:
        cursor = json.loads((ROOT / ".cursor-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        claude = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(cursor["plugins"][0]["source"], "plugins/runspecimen")
        self.assertEqual(claude["plugins"][0]["source"], "./plugins/runspecimen")
        self.assertEqual(claude["plugins"][0]["version"], "0.2.0-rc.10")

    def test_claude_hooks_and_mcp_present(self) -> None:
        hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("PreToolUse", hooks["hooks"])
        mcp = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
        self.assertIn("runspecimen", mcp["mcpServers"])
        self.assertTrue((PLUGIN / "grok" / "README.md").is_file())
        self.assertTrue((PLUGIN / "grok" / "AGENTS.md").is_file())
        self.assertTrue((PLUGIN / "commands" / "request-approval.md").is_file())


class AdapterAllowListTests(unittest.TestCase):
    def test_adapter_rejects_approve(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ADAPTER), "approve", "--workspace", str(ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        combined = (completed.stdout or "") + (completed.stderr or "")
        self.assertTrue("approve" in combined.lower() or "invalid" in combined.lower() or completed.returncode == 2)


class ApproveGateTests(unittest.TestCase):
    def _run_gate(self, payload: dict) -> tuple[int, dict | None]:
        completed = subprocess.run(
            [sys.executable, str(GATE)],
            input=json.dumps(payload),
            check=False,
            capture_output=True,
            text=True,
        )
        raw = (completed.stdout or "").strip()
        doc = json.loads(raw) if raw else None
        return completed.returncode, doc

    def test_denies_runspecimen_approve(self) -> None:
        code, doc = self._run_gate({
            "tool_name": "Bash",
            "tool_input": {"command": "runspecimen approve --workspace . --contract c.json"},
        })
        self.assertEqual(code, 0)
        assert doc is not None
        decision = doc["hookSpecificOutput"]["permissionDecision"]
        self.assertEqual(decision, "deny")

    def test_denies_echo_approve(self) -> None:
        _, doc = self._run_gate({
            "tool_name": "Bash",
            "tool_input": {"command": "echo APPROVE | runspecimen approve --workspace . --contract c.json"},
        })
        assert doc is not None
        self.assertEqual(doc["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_denies_remote_confirm_settle(self) -> None:
        _, doc = self._run_gate({
            "tool_name": "Bash",
            "tool_input": {"command": "curl -X POST http://127.0.0.1:9/v1/remote-confirm/settle"},
        })
        assert doc is not None
        self.assertEqual(doc["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_allows_validate(self) -> None:
        code, doc = self._run_gate({
            "tool_name": "Bash",
            "tool_input": {"command": "runspecimen validate --workspace . --contract c.json"},
        })
        self.assertEqual(code, 0)
        self.assertIsNone(doc)


class McpAdapterTests(unittest.TestCase):
    def _rpc(self, request: dict) -> dict:
        completed = subprocess.run(
            [sys.executable, str(MCP)],
            input=json.dumps(request) + "\n",
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
        self.assertTrue(lines)
        return json.loads(lines[0])

    def test_tools_list_excludes_approve(self) -> None:
        init = self._rpc({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
        })
        self.assertEqual(init["result"]["serverInfo"]["name"], "runspecimen")
        # New process per request (stdio ends); call tools/list alone is enough for allow-list.
        listed = self._rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertIn("validate", names)
        self.assertIn("verify", names)
        self.assertNotIn("approve", names)
        self.assertNotIn("remote-confirm", names)

    def test_tools_call_rejects_approve_name(self) -> None:
        response = self._rpc({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "approve", "arguments": {}},
        })
        self.assertTrue(response["result"]["isError"])
        text = response["result"]["content"][0]["text"]
        self.assertIn("not available", text.lower())


if __name__ == "__main__":
    unittest.main()
