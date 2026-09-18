"""Plugin adapter and approve-gate coverage for Codex/Cursor/Claude/Grok/Gemini/Junie/Windsurf."""

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
IDE_ACTIONS = PLUGIN / "jetbrains" / "scripts" / "ide_actions.py"


class PluginManifestTests(unittest.TestCase):
    def test_host_manifests_share_version_and_name(self) -> None:
        expected = "0.2.0-rc.10"
        manifests = {
            "codex": PLUGIN / ".codex-plugin" / "plugin.json",
            "cursor": PLUGIN / ".cursor-plugin" / "plugin.json",
            "claude": PLUGIN / ".claude-plugin" / "plugin.json",
            "gemini": PLUGIN / "gemini-extension.json",
        }
        loaded = {key: json.loads(path.read_text(encoding="utf-8")) for key, path in manifests.items()}
        for key, doc in loaded.items():
            self.assertEqual(doc.get("name"), "runspecimen", key)
            version = str(doc.get("version", "")).split("+", 1)[0]
            self.assertEqual(version, expected, key)

    def test_marketplaces_point_at_plugin(self) -> None:
        cursor = json.loads((ROOT / ".cursor-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        claude = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        junie = json.loads((ROOT / ".junie-extension" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(cursor["plugins"][0]["source"], "plugins/runspecimen")
        self.assertEqual(claude["plugins"][0]["source"], "./plugins/runspecimen")
        self.assertEqual(claude["plugins"][0]["version"], "0.2.0-rc.10")
        self.assertEqual(junie["extensions"][0]["source"], "./plugins/runspecimen")
        self.assertEqual(junie["extensions"][0]["version"], "0.2.0-rc.10")

    def test_claude_hooks_and_mcp_present(self) -> None:
        hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        claude_hooks = json.loads((PLUGIN / "hooks" / "claude-hooks.json").read_text(encoding="utf-8"))
        self.assertIn("BeforeTool", hooks["hooks"])
        self.assertNotIn("PreToolUse", hooks["hooks"])
        self.assertIn("PreToolUse", claude_hooks["hooks"])
        self.assertNotIn("BeforeTool", claude_hooks["hooks"])
        claude_plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(claude_plugin.get("hooks"), "./hooks/claude-hooks.json")
        mcp = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
        self.assertIn("runspecimen", mcp["mcpServers"])
        self.assertTrue((PLUGIN / "grok" / "README.md").is_file())
        self.assertTrue((PLUGIN / "grok" / "AGENTS.md").is_file())
        self.assertTrue((PLUGIN / "commands" / "request-approval.md").is_file())

    def test_gemini_windsurf_jetbrains_files_present(self) -> None:
        self.assertTrue((PLUGIN / "GEMINI.md").is_file())
        self.assertTrue((PLUGIN / "gemini" / "README.md").is_file())
        self.assertTrue((PLUGIN / "commands" / "validate.toml").is_file())
        self.assertTrue((PLUGIN / "commands" / "request-approval.toml").is_file())
        self.assertTrue((PLUGIN / "extension.json").is_file())
        self.assertTrue((PLUGIN / "jetbrains" / "README.md").is_file())
        self.assertTrue((PLUGIN / "jetbrains" / "intellij-plugin" / "src" / "main" / "resources" / "META-INF" / "plugin.xml").is_file())
        self.assertTrue((PLUGIN / "windsurf" / "skills" / "runspecimen" / "SKILL.md").is_file())
        self.assertTrue((PLUGIN / "windsurf" / "rules" / "runspecimen.md").is_file())
        gemini = json.loads((PLUGIN / "gemini-extension.json").read_text(encoding="utf-8"))
        self.assertIn("runspecimen", gemini["mcpServers"])
        self.assertTrue(any("approve" in item for item in gemini.get("excludeTools", [])))
        plugin_xml = (PLUGIN / "jetbrains" / "intellij-plugin" / "src" / "main" / "resources" / "META-INF" / "plugin.xml").read_text(encoding="utf-8")
        self.assertNotIn("ApproveAction", plugin_xml)
        self.assertIn("RequestApprovalAction", plugin_xml)


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
    def _run_gate(self, payload: dict, extra_args: list[str] | None = None) -> tuple[int, dict | None]:
        completed = subprocess.run(
            [sys.executable, str(GATE), *(extra_args or [])],
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

    def test_denies_remote_confirm_refuse_http(self) -> None:
        _, doc = self._run_gate({
            "tool_name": "Bash",
            "tool_input": {"command": "curl -X POST http://127.0.0.1:9/v1/remote-confirm-refuse"},
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

    def test_gemini_format_deny(self) -> None:
        code, doc = self._run_gate(
            {
                "hook_event_name": "BeforeTool",
                "tool_name": "run_shell_command",
                "tool_input": {"command": "runspecimen approve --workspace . --contract c.json"},
            },
            extra_args=["--format", "gemini"],
        )
        self.assertEqual(code, 0)
        assert doc is not None
        self.assertEqual(doc.get("decision"), "deny")
        self.assertIn("TTY", doc.get("reason", ""))
        self.assertNotIn("hookSpecificOutput", doc)

    def test_auto_detects_gemini_beforetool(self) -> None:
        _, doc = self._run_gate({
            "hook_event_name": "BeforeTool",
            "tool_name": "run_shell_command",
            "tool_input": {"command": "echo APPROVE"},
        })
        assert doc is not None
        self.assertEqual(doc.get("decision"), "deny")

    def test_denies_mcp_tool_name_approve(self) -> None:
        _, doc = self._run_gate(
            {
                "hook_event_name": "BeforeTool",
                "tool_name": "mcp_runspecimen_approve",
                "tool_input": {},
            },
            extra_args=["--format", "gemini"],
        )
        assert doc is not None
        self.assertEqual(doc.get("decision"), "deny")

    def test_denies_ide_actions_approve_shell(self) -> None:
        _, doc = self._run_gate({
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 plugins/runspecimen/jetbrains/scripts/ide_actions.py approve --workspace .",
            },
        })
        assert doc is not None
        self.assertEqual(doc["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_allows_discuss_approve_lowercase(self) -> None:
        code, doc = self._run_gate({
            "tool_name": "Bash",
            "tool_input": {"command": "echo remember human must approve in tty"},
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


class JetBrainsIdeActionTests(unittest.TestCase):
    def test_request_approval_prints_handoff_only(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(IDE_ACTIONS),
                "request-approval",
                "--workspace",
                str(ROOT),
                "--contract",
                str(ROOT / "examples" / "demo_contract.json"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        out = completed.stdout or ""
        self.assertIn("runspecimen approve", out)
        self.assertIn("Human TTY approval required", out)
        self.assertNotIn("APPROVE\n", out)

    def test_rejects_approve_action_name(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(IDE_ACTIONS), "approve", "--workspace", str(ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        combined = (completed.stdout or "") + (completed.stderr or "")
        self.assertTrue("approve" in combined.lower() or "invalid" in combined.lower() or completed.returncode == 2)


if __name__ == "__main__":
    unittest.main()
