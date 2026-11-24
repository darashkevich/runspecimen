"""Invalid MCP requests must not launch the CLI or kill subsequent requests."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / 'plugins/runspecimen/scripts/runspecimen_mcp.py'
spec = importlib.util.spec_from_file_location('mcp_validation', MCP)
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


class TestMCPValidation(unittest.TestCase):
    def test_invalid_arguments_never_resolve_or_launch_cli(self):
        cases = [('about', value) for value in (None, [], '', False, {'shell': 'x'})]
        for tool in mcp.TOOLS:
            name, schema = tool['name'], tool['inputSchema']
            valid = {key: '/tmp/value' for key in schema.get('required', [])}
            for key in valid:
                cases.append((name, {k: v for k, v in valid.items() if k != key}))
            for key, prop in schema['properties'].items():
                invalid = ('yes', 1, None) if prop['type'] == 'boolean' else (False, 1, [], {}, None, '', ' ', '\t', 'a\x00b')
                cases.extend((name, dict(valid, **{key: value})) for value in invalid)
            cases.append((name, dict(valid, unexpected='x')))
        with patch.object(mcp.shutil, 'which') as which, patch.object(mcp.subprocess, 'run') as run:
            for name, arguments in cases:
                with self.subTest(name=name, arguments=arguments):
                    self.assertTrue(mcp._run_cli(name, arguments)['isError'])
            which.assert_not_called()
            run.assert_not_called()

    def test_allowed_action_without_schema_fails_closed(self):
        with patch.object(mcp, 'TOOLS', []), patch.object(mcp.shutil, 'which') as which, patch.object(
            mcp.subprocess, 'run'
        ) as run:
            response = mcp._handle({'id': 1, 'method': 'tools/call',
                                    'params': {'name': 'about', 'arguments': {}}})
            self.assertTrue(response['result']['isError'])
            self.assertIn('No argument schema', response['result']['content'][0]['text'])
            self.assertEqual(mcp._handle({'id': 2, 'method': 'ping'})['result'], {})
            which.assert_not_called()
            run.assert_not_called()

    def test_bad_arguments_do_not_kill_either_server(self):
        requests = [{'id': i, 'method': 'tools/call',
                     'params': {'name': 'about', 'arguments': arguments}}
                    for i, arguments in enumerate((None, [], '', False, 1))]
        requests.append({'id': 99, 'method': 'ping'})
        for path in (MCP, ROOT / 'plugins/runspecimen/antigravity/scripts/runspecimen_mcp.py'):
            result = subprocess.run([sys.executable, str(path)], text=True, capture_output=True,
                                    input=''.join(json.dumps(r) + '\n' for r in requests), check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(responses), len(requests))
            self.assertTrue(all(r['result']['isError'] for r in responses[:-1]))
            self.assertEqual(responses[-1], {'jsonrpc': '2.0', 'id': 99, 'result': {}})

    def test_valid_schema_arguments_reach_cli(self):
        for tool in mcp.TOOLS:
            schema = tool['inputSchema']
            arguments = {key: (False if prop['type'] == 'boolean' else '/tmp/with spaces')
                         for key, prop in schema['properties'].items()}
            with patch.object(mcp.shutil, 'which', return_value='/cli'), patch.object(
                mcp.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ok', '')
            ) as run:
                self.assertFalse(mcp._run_cli(tool['name'], arguments)['isError'])
                self.assertEqual(run.call_count, 1)
                self.assertNotIn('shell', run.call_args.kwargs)

    def test_malformed_params_do_not_kill_either_server(self):
        requests = [{'id': i, 'method': 'tools/call', 'params': params}
                    for i, params in enumerate(([], 'bad', True, 5, None, {'name': []}))]
        requests.append({'id': 99, 'method': 'ping'})
        for path in (MCP, ROOT / 'plugins/runspecimen/antigravity/scripts/runspecimen_mcp.py'):
            result = subprocess.run([sys.executable, str(path)], text=True, capture_output=True,
                                    input=''.join(json.dumps(r) + '\n' for r in requests), check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(responses), len(requests))
            self.assertTrue(all(r['error']['code'] == -32602 for r in responses[:-1]))
            self.assertEqual(responses[-1], {'jsonrpc': '2.0', 'id': 99, 'result': {}})
