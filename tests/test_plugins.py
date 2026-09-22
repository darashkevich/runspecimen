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
        expected = "0.2.0-rc.13"
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
        self.assertEqual(claude["plugins"][0]["version"], "0.2.0-rc.13")
        self.assertEqual(junie["extensions"][0]["source"], "./plugins/runspecimen")
        self.assertEqual(junie["extensions"][0]["version"], "0.2.0-rc.13")

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



class PluginApproveBoundaryExtras(unittest.TestCase):
    """High-value gaps beyond the base approve-gate suite (Track F)."""

    LIFECYCLE = frozenset({
        "about", "dashboard", "doctor", "validate", "status",
        "preflight", "run", "postflight", "verify",
    })

    def test_adapter_and_mcp_allowed_sets_match_lifecycle_only(self) -> None:
        adapter_src = ADAPTER.read_text(encoding="utf-8")
        mcp_src = MCP.read_text(encoding="utf-8")
        self.assertIn("ALLOWED = frozenset({", adapter_src)
        self.assertIn("ALLOWED = frozenset({", mcp_src)
        # Import ALLOWED without executing PATH-dependent main paths.
        import importlib.util

        def load_allowed(path: Path) -> frozenset[str]:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return frozenset(mod.ALLOWED)

        adapter_allowed = load_allowed(ADAPTER)
        mcp_allowed = load_allowed(MCP)
        self.assertEqual(adapter_allowed, self.LIFECYCLE)
        self.assertEqual(mcp_allowed, self.LIFECYCLE)
        self.assertEqual(adapter_allowed, mcp_allowed)
        for forbidden in ("approve", "shell", "execute", "remote-confirm", "settle"):
            self.assertNotIn(forbidden, adapter_allowed)
            self.assertNotIn(forbidden, mcp_allowed)

    def test_adapter_rejects_shell_execute_settle_names(self) -> None:
        for action in ("shell", "execute", "remote-confirm", "settle", "approve"):
            completed = subprocess.run(
                [sys.executable, str(ADAPTER), action, "--workspace", str(ROOT)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0, action)

    def test_mcp_tools_list_equals_lifecycle_and_rejects_shell_execute_settle(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(MCP)],
            input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) + "\n",
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        listed = json.loads(completed.stdout.strip().splitlines()[0])
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertEqual(names, self.LIFECYCLE)
        for bad in ("approve", "shell", "execute", "settle", "remote-confirm"):
            response = subprocess.run(
                [sys.executable, str(MCP)],
                input=json.dumps({
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": bad, "arguments": {}},
                }) + "\n",
                check=False,
                capture_output=True,
                text=True,
            )
            doc = json.loads(response.stdout.strip().splitlines()[0])
            self.assertTrue(doc["result"]["isError"], bad)

    def test_mcp_instructions_require_tty_approve(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(MCP)],
            input=json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            }) + "\n",
            check=False,
            capture_output=True,
            text=True,
        )
        doc = json.loads(completed.stdout.strip().splitlines()[0])
        instructions = json.dumps(doc).lower()
        self.assertTrue("tty" in instructions or "approve" in instructions)

    def _gate(self, payload: dict, extra: list[str] | None = None) -> dict | None:
        completed = subprocess.run(
            [sys.executable, str(GATE), *(extra or [])],
            input=json.dumps(payload),
            check=False,
            capture_output=True,
            text=True,
        )
        raw = (completed.stdout or "").strip()
        return json.loads(raw) if raw else None

    def test_gate_denies_printf_and_python_m_approve(self) -> None:
        for command in (
            "printf APPROVE | runspecimen approve --workspace . --contract c.json",
            "python -m runspecimen approve --workspace . --contract c.json",
            "python3 -m runspecimen approve --workspace . --contract c.json",
        ):
            doc = self._gate({"tool_name": "Bash", "tool_input": {"command": command}})
            assert doc is not None
            self.assertEqual(doc["hookSpecificOutput"]["permissionDecision"], "deny", command)

    def test_gate_denies_claude_mcp_tool_name_and_nested_arguments(self) -> None:
        doc = self._gate({
            "tool_name": "mcp__runspecimen__approve",
            "tool_input": {},
        })
        assert doc is not None
        self.assertEqual(doc["hookSpecificOutput"]["permissionDecision"], "deny")
        doc = self._gate({
            "tool_name": "Bash",
            "arguments": {"command": "runspecimen approve --workspace . --contract c.json"},
        })
        assert doc is not None
        self.assertEqual(doc["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_gate_denies_companion_v1_approve_path(self) -> None:
        doc = self._gate({
            "tool_name": "Bash",
            "tool_input": {"command": "curl -X POST http://127.0.0.1:9/v1/approve"},
        })
        assert doc is not None
        self.assertEqual(doc["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_gate_claude_format_forced(self) -> None:
        doc = self._gate(
            {
                "hook_event_name": "BeforeTool",
                "tool_name": "Bash",
                "tool_input": {"command": "echo APPROVE"},
            },
            extra=["--format", "claude"],
        )
        assert doc is not None
        self.assertIn("hookSpecificOutput", doc)
        self.assertEqual(doc["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_skills_rules_commands_forbid_typing_approve(self) -> None:
        paths = [
            PLUGIN / "skills" / "runspecimen" / "SKILL.md",
            PLUGIN / "windsurf" / "skills" / "runspecimen" / "SKILL.md",
            PLUGIN / "windsurf" / "rules" / "runspecimen.md",
            PLUGIN / "commands" / "request-approval.md",
            PLUGIN / "grok" / "AGENTS.md",
            PLUGIN / "GEMINI.md",
        ]
        for path in paths:
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8").lower()
            self.assertTrue(
                "never type" in text
                or "must not" in text
                or "do not type" in text
                or "do not" in text and "approve" in text,
                path,
            )
            self.assertTrue("pipe" in text or "tty" in text or "real terminal" in text, path)

    def test_hooks_wire_claude_and_gemini_gates(self) -> None:
        claude = json.loads((PLUGIN / "hooks" / "claude-hooks.json").read_text(encoding="utf-8"))
        gemini = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("PreToolUse", claude["hooks"])
        self.assertIn("BeforeTool", gemini["hooks"])
        claude_blob = json.dumps(claude)
        gemini_blob = json.dumps(gemini)
        self.assertIn("block_approve_gate.py", claude_blob)
        self.assertIn("block_approve_gate.py", gemini_blob)
        gemini_ext = json.loads((PLUGIN / "gemini-extension.json").read_text(encoding="utf-8"))
        self.assertTrue(any("approve" in str(item).lower() for item in gemini_ext.get("excludeTools", [])))

    def test_plugin_scripts_have_no_network_phone_home(self) -> None:
        forbidden_imports = ("urllib.request", "http.client", "requests", "aiohttp")
        for path in (ADAPTER, GATE, MCP, IDE_ACTIONS):
            text = path.read_text(encoding="utf-8")
            for item in forbidden_imports:
                self.assertNotIn(f"import {item}", text, path.name)
                self.assertNotIn(f"from {item}", text, path.name)
            # No outbound URL literals; deny-docs may say "no network phone-home".
            for url in ("https://", "http://"):
                residual = text.lower().replace("http://127.0.0.1", "")
                self.assertNotIn(url, residual, path.name)



if __name__ == "__main__":
    unittest.main()
