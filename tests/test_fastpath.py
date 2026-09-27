"""Deterministic fast-path invariants. A spy provider fails the test if invoked."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT, SRC

from runspecimen.artifact import SCHEMA_KINDS
from runspecimen.evalsuite import (
    EvalError,
    register_eval_provider,
    run_eval_suite,
    unregister_eval_provider,
)
from runspecimen.fastpath import (
    FastpathError,
    complete_fastpath_request,
    normalize_fastpath_text,
    parse_fastpath_config,
)


class SpyModelProvider:
    name = "spy_model"

    def __init__(self) -> None:
        self.calls = 0
        self.tasks: list[dict] = []

    def run_task(self, *, workspace: Path, task: dict) -> dict:
        self.calls += 1
        self.tasks.append(task)
        return {
            "outcome": "model_ran",
            "deterministic": False,
            "llm_input_tokens": 11,
            "llm_output_tokens": 7,
        }


def _rules(**kwargs):
    doc = {
        "enabled": True,
        "rules": [
            {
                "id": "gratitude",
                "exact": ["thanks", "thank you"],
                "outcome": {"type": "respond", "text": "You're welcome."},
            },
            {
                "id": "acknowledgement",
                "exact": ["ok", "okay", "got it"],
                "outcome": {"type": "no_response"},
            },
        ],
    }
    doc.update(kwargs)
    return parse_fastpath_config(doc, require_kind=False)


class NormalizeTests(unittest.TestCase):
    def test_lowercase_and_casefold(self) -> None:
        self.assertEqual(normalize_fastpath_text("thank you"), "thank you")
        self.assertEqual(normalize_fastpath_text("Thank You"), "thank you")
        self.assertEqual(normalize_fastpath_text("THANKS"), "thanks")

    def test_outer_and_internal_whitespace(self) -> None:
        self.assertEqual(normalize_fastpath_text("  THANK   YOU!!!  "), "thank you")

    def test_terminal_punctuation_only(self) -> None:
        self.assertEqual(normalize_fastpath_text("thank you!"), "thank you")
        self.assertEqual(normalize_fastpath_text("thank you."), "thank you")
        self.assertEqual(normalize_fastpath_text("thank you..."), "thank you")

    def test_question_comma_emoji_and_suffix_remain(self) -> None:
        self.assertEqual(normalize_fastpath_text("thank you?"), "thank you?")
        self.assertEqual(normalize_fastpath_text("thank you, but..."), "thank you, but")
        self.assertEqual(normalize_fastpath_text("thank you 🙏"), "thank you 🙏")
        self.assertEqual(normalize_fastpath_text("ok, continue"), "ok, continue")
        self.assertEqual(normalize_fastpath_text("ok?"), "ok?")


class ConfigValidationTests(unittest.TestCase):
    def test_duplicate_rule_id(self) -> None:
        with self.assertRaises(FastpathError):
            parse_fastpath_config(
                {
                    "enabled": True,
                    "rules": [
                        {
                            "id": "gratitude",
                            "exact": ["thanks"],
                            "outcome": {"type": "respond", "text": "x"},
                        },
                        {
                            "id": "gratitude",
                            "exact": ["ty"],
                            "outcome": {"type": "respond", "text": "y"},
                        },
                    ],
                },
                require_kind=False,
            )

    def test_normalized_collision_is_order_independent(self) -> None:
        with self.assertRaises(FastpathError) as ctx:
            parse_fastpath_config(
                {
                    "enabled": True,
                    "rules": [
                        {
                            "id": "rule_a",
                            "exact": ["Thank you!"],
                            "outcome": {"type": "respond", "text": "A"},
                        },
                        {
                            "id": "rule_b",
                            "exact": ["thank   you"],
                            "outcome": {"type": "respond", "text": "B"},
                        },
                    ],
                },
                require_kind=False,
            )
        self.assertIn("rule_a", str(ctx.exception))
        self.assertIn("rule_b", str(ctx.exception))

    def test_empty_match_and_empty_normalized(self) -> None:
        with self.assertRaises(FastpathError):
            parse_fastpath_config(
                {
                    "enabled": True,
                    "rules": [
                        {
                            "id": "empty",
                            "exact": [],
                            "outcome": {"type": "respond", "text": "x"},
                        }
                    ],
                },
                require_kind=False,
            )
        with self.assertRaises(FastpathError):
            parse_fastpath_config(
                {
                    "enabled": True,
                    "rules": [
                        {
                            "id": "blank",
                            "exact": ["!!!"],
                            "outcome": {"type": "respond", "text": "x"},
                        }
                    ],
                },
                require_kind=False,
            )

    def test_malformed_and_empty_respond_text(self) -> None:
        with self.assertRaises(FastpathError):
            parse_fastpath_config(
                {
                    "enabled": True,
                    "rules": [
                        {
                            "id": "bad",
                            "exact": ["ok"],
                            "outcome": {"type": "wave"},
                        }
                    ],
                },
                require_kind=False,
            )
        with self.assertRaises(FastpathError):
            parse_fastpath_config(
                {
                    "enabled": True,
                    "rules": [
                        {
                            "id": "blanktext",
                            "exact": ["ok"],
                            "outcome": {"type": "respond", "text": "   "},
                        }
                    ],
                },
                require_kind=False,
            )

    def test_valid_outcomes(self) -> None:
        cfg = _rules()
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["index"]["thank you"], "gratitude")
        self.assertEqual(cfg["index"]["ok"], "acknowledgement")


class RequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="rs-fastpath-")
        self.ws = Path(self.tmp.name)
        self.cfg = _rules()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_hit_and_no_response(self) -> None:
        hit = complete_fastpath_request(
            workspace=self.ws, text="  THANK   YOU!!! ", config=self.cfg
        )
        self.assertTrue(hit["ok"])
        self.assertEqual(hit["route"], "fastpath")
        self.assertEqual(hit["rule_id"], "gratitude")
        self.assertEqual(hit["text"], "You're welcome.")
        self.assertFalse(hit["provider_called"])
        self.assertEqual(hit["llm_input_tokens"], 0)
        self.assertEqual(hit["llm_output_tokens"], 0)
        self.assertEqual(hit["llm_inference_cost"], 0)
        self.assertEqual(hit["model_calls_avoided"], 0)
        self.assertEqual(hit["provider_dispatches_avoided"], 0)
        self.assertEqual(hit["deterministic_completions"], 1)
        self.assertIsNone(hit["estimated_token_savings"])

        quiet = complete_fastpath_request(workspace=self.ws, text="OK.", config=self.cfg)
        self.assertTrue(quiet["ok"])
        self.assertEqual(quiet["outcome_type"], "no_response")
        self.assertIsNone(quiet["text"])
        self.assertEqual(quiet["route"], "fastpath")

    def test_near_match_and_question_fall_through(self) -> None:
        for text in (
            "thank you very much",
            "thank you 🙏",
            "thank you, but change section 2",
            "thank you?",
            "ok?",
            "ok, continue",
        ):
            result = complete_fastpath_request(
                workspace=self.ws, text=text, config=self.cfg
            )
            self.assertEqual(result["route"], "fallthrough", text)
            self.assertFalse(result["fastpath_hit"], text)
            self.assertEqual(result["reason"], "no_match", text)

    def test_disabled_and_absent(self) -> None:
        disabled = complete_fastpath_request(
            workspace=self.ws, text="thank you", config=_rules(enabled=False)
        )
        self.assertEqual(disabled["reason"], "disabled")
        absent = complete_fastpath_request(
            workspace=self.ws, text="thank you", config=None
        )
        self.assertEqual(absent["reason"], "absent")
        self.assertFalse(absent["provider_called"])

    def test_pending_confirmation_and_approve_are_not_swallowed(self) -> None:
        import os
        import time

        root = self.ws / ".runspecimen"
        root.mkdir(parents=True)
        pending = root / "remote_confirm_pending.json"

        def ask(name: str) -> dict:
            return complete_fastpath_request(workspace=self.ws, text="ok", config=self.cfg)

        pending.write_text("{}", encoding="utf-8")
        empty = ask("empty")
        self.assertTrue(empty["fastpath_hit"])
        self.assertNotEqual(empty["reason"], "unsafe_pending_confirmation")

        pending.write_text(
            json.dumps({"consumed": True, "expires_at_unix": time.time() + 3600}),
            encoding="utf-8",
        )
        consumed = ask("consumed")
        self.assertTrue(consumed["fastpath_hit"])

        pending.write_text(
            json.dumps({"consumed": False, "expires_at_unix": 0}),
            encoding="utf-8",
        )
        expired = ask("expired")
        self.assertTrue(expired["fastpath_hit"])

        pending.write_text(
            json.dumps({"consumed": False, "expires_at_unix": time.time() + 3600}),
            encoding="utf-8",
        )
        self.assertEqual(ask("live")["reason"], "unsafe_pending_confirmation")

        pending.unlink()
        nested = root / "nested" / "remote_confirm_pending.json"
        nested.parent.mkdir()
        nested.write_text(
            json.dumps({"consumed": False, "expires_at_unix": time.time() + 3600}),
            encoding="utf-8",
        )
        self.assertEqual(ask("nested-live")["reason"], "unsafe_pending_confirmation")
        nested.write_text(
            json.dumps({"consumed": True, "expires_at_unix": 0}),
            encoding="utf-8",
        )
        self.assertTrue(ask("nested-stale")["fastpath_hit"])

        nested.write_text("{", encoding="utf-8")
        self.assertEqual(ask("malformed")["reason"], "unsafe_pending_confirmation")

        nested.write_text("{}", encoding="utf-8")
        os.chmod(nested, 0)
        try:
            self.assertEqual(ask("unreadable")["reason"], "unsafe_pending_confirmation")
        finally:
            os.chmod(nested, 0o644)

        hidden = root / "sealed"
        hidden.mkdir()
        (hidden / "remote_confirm_pending.json").write_text(
            json.dumps({"consumed": True, "expires_at_unix": 0}),
            encoding="utf-8",
        )
        os.chmod(hidden, 0)
        try:
            self.assertEqual(ask("sealed-dir")["reason"], "unsafe_pending_confirmation")
        finally:
            os.chmod(hidden, 0o755)

        approve = complete_fastpath_request(
            workspace=self.ws, text="APPROVE", config=self.cfg
        )
        self.assertEqual(approve["reason"], "unsafe_approval_phrase")


class EvalDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="rs-fastpath-eval-")
        self.ws = Path(self.tmp.name)
        self.spy = SpyModelProvider()
        register_eval_provider(self.spy)

    def tearDown(self) -> None:
        unregister_eval_provider(self.spy.name)
        self.tmp.cleanup()

    def _suite(self, tasks, fastpath=None):
        doc = {
            "schema_kind": "eval_suite",
            "schema_version": 1,
            "id": "fastpath-suite",
            "description": "fastpath tests",
            "tasks": tasks,
        }
        if fastpath is not None:
            doc["fastpath"] = fastpath
        return doc

    def test_hit_never_crosses_provider_dispatch(self) -> None:
        result = run_eval_suite(
            workspace=self.ws,
            suite=self._suite(
                [
                    {
                        "id": "thanks-task",
                        "provider": self.spy.name,
                        "judgment": "model",
                        "capability": "text_completion",
                        "input": "Thank you!",
                    }
                ],
                fastpath={
                    "enabled": True,
                    "rules": [
                        {
                            "id": "gratitude",
                            "exact": ["thank you"],
                            "outcome": {"type": "respond", "text": "You're welcome."},
                        }
                    ],
                },
            ),
        )
        self.assertEqual(self.spy.calls, 0)
        task = result["tasks"][0]
        self.assertEqual(task["route"], "fastpath")
        self.assertEqual(task["rule_id"], "gratitude")
        self.assertFalse(task["provider_called"])
        self.assertEqual(task["llm_input_tokens"], 0)
        self.assertEqual(task["llm_output_tokens"], 0)
        self.assertEqual(task["llm_inference_cost"], 0)
        self.assertEqual(task["provider_result"]["text"], "You're welcome.")
        self.assertEqual(task["actual_outcome"], "text_completed")
        self.assertFalse(task["conclusive"])
        self.assertFalse(result["passed_deterministic"])
        self.assertEqual(result["fastpath"]["model_calls_avoided"], 1)
        self.assertEqual(result["fastpath"]["provider_dispatches_avoided"], 1)
        self.assertEqual(result["fastpath"]["deterministic_completions"], 1)

    def test_unmatched_uses_existing_provider_path(self) -> None:
        result = run_eval_suite(
            workspace=self.ws,
            suite=self._suite(
                [
                    {
                        "id": "near",
                        "provider": self.spy.name,
                        "judgment": "model",
                        "capability": "text_completion",
                        "input": "thank you very much",
                    }
                ],
                fastpath={
                    "enabled": True,
                    "rules": [
                        {
                            "id": "gratitude",
                            "exact": ["thank you"],
                            "outcome": {"type": "respond", "text": "You're welcome."},
                        }
                    ],
                },
            ),
        )
        self.assertEqual(self.spy.calls, 1)
        task = result["tasks"][0]
        self.assertEqual(task["route"], "provider")
        self.assertTrue(task["provider_called"])
        self.assertEqual(task["llm_input_tokens"], 11)
        self.assertEqual(task["llm_output_tokens"], 7)
        self.assertEqual(task["actual_outcome"], "model_ran")
        self.assertEqual(task["reason"], "no_match")
        self.assertEqual(task["actual_llm_tokens_used"], 18)
        self.assertIsNone(task["llm_inference_cost"])
        self.assertIsNone(task["actual_llm_cost"])

    def test_absent_fastpath_preserves_provider_behavior(self) -> None:
        run_eval_suite(
            workspace=self.ws,
            suite=self._suite(
                [
                    {
                        "id": "plain",
                        "provider": self.spy.name,
                        "judgment": "model",
                        "input": "thank you",
                    }
                ]
            ),
        )
        self.assertEqual(self.spy.calls, 1)

    def test_structured_action_is_not_intercepted(self) -> None:
        run_eval_suite(
            workspace=self.ws,
            suite=self._suite(
                [
                    {
                        "id": "toolish",
                        "provider": self.spy.name,
                        "judgment": "model",
                        "capability": "text_completion",
                        "input": "ok",
                        "action": "delete-records",
                    }
                ],
                fastpath={
                    "enabled": True,
                    "rules": [
                        {
                            "id": "acknowledgement",
                            "exact": ["ok"],
                            "outcome": {"type": "no_response"},
                        }
                    ],
                },
            ),
        )
        self.assertEqual(self.spy.calls, 1)

    def test_invalid_embedded_fastpath_is_a_config_error(self) -> None:
        with self.assertRaises(EvalError):
            run_eval_suite(
                workspace=self.ws,
                suite=self._suite(
                    [{"id": "t", "provider": self.spy.name}],
                    fastpath={
                        "enabled": True,
                        "rules": [
                            {
                                "id": "a",
                                "exact": ["Thank you!"],
                                "outcome": {"type": "respond", "text": "A"},
                            },
                            {
                                "id": "b",
                                "exact": ["thank   you"],
                                "outcome": {"type": "respond", "text": "B"},
                            },
                        ],
                    },
                ),
            )
        self.assertEqual(self.spy.calls, 0)


class DashboardStatsTests(unittest.TestCase):
    def test_latest_eval_result_is_summarized(self) -> None:
        from runspecimen.dashboard import _fastpath_dashboard_stats
        from runspecimen.evalsuite import write_eval_result

        with tempfile.TemporaryDirectory(prefix="rs-fp-dash-") as raw:
            ws = Path(raw)
            empty = _fastpath_dashboard_stats(ws)
            self.assertEqual(empty["fastpath_executions"], 0)
            spy = SpyModelProvider()
            register_eval_provider(spy)
            try:
                result = run_eval_suite(
                    workspace=ws,
                    suite={
                        "schema_kind": "eval_suite",
                        "schema_version": 1,
                        "id": "dash",
                        "description": "dash",
                        "fastpath": {
                            "enabled": True,
                            "rules": [
                                {
                                    "id": "gratitude",
                                    "exact": ["thank you"],
                                    "outcome": {
                                        "type": "respond",
                                        "text": "You're welcome.",
                                    },
                                }
                            ],
                        },
                        "tasks": [
                            {
                                "id": "t",
                                "provider": spy.name,
                                "judgment": "model",
                                "capability": "text_completion",
                                "input": "thank you",
                            }
                        ],
                    },
                )
                write_eval_result(ws, result)
            finally:
                unregister_eval_provider(spy.name)
            stats = _fastpath_dashboard_stats(ws)
            self.assertEqual(stats["fastpath_executions"], 1)
            self.assertEqual(stats["model_calls_avoided"], 1)
            self.assertEqual(spy.calls, 0)


class CliAndSchemaTests(unittest.TestCase):
    def test_schema_kind_is_registered(self) -> None:
        self.assertIn("fastpath_config", SCHEMA_KINDS)

    def test_eval_complete_cli(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-fp-cli-") as raw:
            ws = Path(raw)
            cfg = ws / "fastpath.json"
            cfg.write_text(
                json.dumps(
                    {
                        "schema_kind": "fastpath_config",
                        "schema_version": 1,
                        "enabled": True,
                        "rules": [
                            {
                                "id": "gratitude",
                                "exact": ["thank you"],
                                "outcome": {
                                    "type": "respond",
                                    "text": "You're welcome.",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "runspecimen",
                    "eval",
                    "complete",
                    "--workspace",
                    str(ws),
                    "--config",
                    str(cfg),
                    "--input",
                    "Thank you!",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(ROOT),
                env={**dict(**__import__("os").environ), "PYTHONPATH": str(SRC)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            body = json.loads(proc.stdout)
            self.assertEqual(body["route"], "fastpath")
            self.assertEqual(body["llm_input_tokens"], 0)
            self.assertEqual(body["llm_output_tokens"], 0)
            self.assertEqual(body["model_calls_avoided"], 0)
            self.assertEqual(body["provider_dispatches_avoided"], 0)
            self.assertFalse(body["provider_called"])


class QaRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="rs-fastpath-qa-")
        self.ws = Path(self.tmp.name)
        self.spy = SpyModelProvider()
        register_eval_provider(self.spy)

    def tearDown(self) -> None:
        unregister_eval_provider(self.spy.name)
        unregister_eval_provider("metered")
        unregister_eval_provider("unknown_usage")
        self.tmp.cleanup()

    def _ack_fastpath(self):
        return {
            "enabled": True,
            "rules": [
                {
                    "id": "acknowledgement",
                    "exact": ["ok"],
                    "outcome": {"type": "no_response"},
                }
            ],
        }

    def _suite(self, tasks, fastpath=None):
        doc = {
            "schema_kind": "eval_suite",
            "schema_version": 1,
            "id": "qa-suite",
            "description": "qa regressions",
            "tasks": tasks,
        }
        if fastpath is not None:
            doc["fastpath"] = fastpath
        return doc

    def test_repeated_parse_and_digest_keep_serialized_fastpath(self) -> None:
        from runspecimen.artifact import bind_artifact_digest
        from runspecimen.evalsuite import parse_eval_suite

        suite = self._suite(
            [
                {
                    "id": "req",
                    "provider": "local_deterministic",
                    "input": "ok",
                    "fixture_dir": "missing-fixture",
                    "contract": "missing.json",
                    "expected_outcome": "passed",
                }
            ],
            fastpath=self._ack_fastpath(),
        )
        first = parse_eval_suite(suite)
        self.assertNotIn("index", first["fastpath"])
        second = parse_eval_suite(first)
        self.assertNotIn("index", second["fastpath"])
        bound = bind_artifact_digest(json.loads(json.dumps(suite)))
        parse_eval_suite(bound)
        disabled = json.loads(json.dumps(suite))
        disabled["fastpath"] = {"enabled": False, "rules": []}
        parse_eval_suite(disabled)
        parse_eval_suite(parse_eval_suite(disabled))
        with self.assertRaises(EvalError):
            parse_eval_suite(
                self._suite(
                    [{"id": "t", "provider": "local_deterministic"}],
                    fastpath={"enabled": True, "rules": [], "index": {"ok": "acknowledgement"}},
                )
            )

    def test_load_then_run_twice_does_not_accept_compiled_index(self) -> None:
        from runspecimen.evalsuite import load_eval_suite

        path = self.ws / "suite.json"
        path.write_text(
            json.dumps(
                self._suite(
                    [
                        {
                            "id": "req",
                            "provider": "local_deterministic",
                            "input": "ok",
                            "fixture_dir": "missing-fixture",
                            "contract": "missing.json",
                            "expected_outcome": "passed",
                            "requires_human": True,
                        }
                    ],
                    fastpath=self._ack_fastpath(),
                )
            ),
            encoding="utf-8",
        )
        loaded = load_eval_suite(path)
        self.assertNotIn("index", loaded["fastpath"])
        first = run_eval_suite(workspace=self.ws, suite=loaded)
        second = run_eval_suite(workspace=self.ws, suite=loaded)
        for result in (first, second):
            task = result["tasks"][0]
            self.assertEqual(task["actual_outcome"], "failed")
            self.assertFalse(task["fastpath_hit"])
            self.assertFalse(result["passed_deterministic"])
            self.assertNotIn("index", loaded["fastpath"])

    def test_phrase_does_not_pass_requirement_tasks(self) -> None:
        fastpath = self._ack_fastpath()
        cases = [
            {"judgment": "deterministic", "requires_human": True},
            {"requires_human": True},
            {"judgment": "model", "requires_human": True},
            {},
        ]
        for extra in cases:
            task = {
                "id": "req",
                "provider": "local_deterministic",
                "input": "ok",
                "fixture_dir": "missing-fixture",
                "contract": "missing.json",
                "expected_outcome": "passed",
                **extra,
            }
            result = run_eval_suite(
                workspace=self.ws,
                suite=self._suite([task], fastpath=fastpath),
            )
            recorded = result["tasks"][0]
            self.assertEqual(recorded["actual_outcome"], "failed", extra)
            self.assertFalse(recorded["fastpath_hit"], extra)
            self.assertFalse(recorded["conclusive"], extra)
            self.assertFalse(result["passed_deterministic"], extra)
            self.assertEqual(result["fastpath"]["model_calls_avoided"], 0, extra)

    def test_invalid_contract_and_unauthorized_check_stay_off_fastpath(self) -> None:
        from tests.helpers import base_contract, write_contract
        from runspecimen.artifact import bind_artifact_digest
        from runspecimen.atomic import atomic_write_json
        from runspecimen.hashutil import sha256_file

        fix = self.ws / "fixture"
        fix.mkdir()
        (fix / "missing.json").write_text("{", encoding="utf-8")
        with self.assertRaises(Exception) as ctx:
            run_eval_suite(
                workspace=self.ws,
                suite=self._suite(
                    [
                        {
                            "id": "bad-contract",
                            "provider": "local_deterministic",
                            "input": "ok",
                            "fixture_dir": "fixture",
                            "contract": "missing.json",
                            "expected_outcome": "passed",
                            "requires_human": True,
                        }
                    ],
                    fastpath=self._ack_fastpath(),
                ),
            )
        self.assertNotIn("unknown field", str(ctx.exception))

        manifest_path = fix / "manifest.json"
        atomic_write_json(
            manifest_path,
            bind_artifact_digest(
                {
                    "schema_kind": "task_manifest",
                    "schema_version": 1,
                    "id": "m-fail",
                    "description": "failing check",
                    "requirements": [
                        {
                            "id": "r-fail",
                            "description": "exit mismatch",
                            "inputs": [],
                            "source_scope": [],
                            "required_evidence": [],
                            "expected": {},
                            "check": {
                                "provider": "command_status",
                                "id": "c",
                                "config": {
                                    "argv": [sys.executable, "-c", "raise SystemExit(2)"],
                                    "exit_code": 0,
                                },
                            },
                        }
                    ],
                }
            ),
        )
        contract = base_contract(run_id="run-fail")
        contract["task_manifest"] = {
            "id": "m-fail",
            "path": "manifest.json",
            "sha256": sha256_file(manifest_path),
        }
        write_contract(fix, "contract.json", contract)
        result = run_eval_suite(
            workspace=self.ws,
            suite=self._suite(
                [
                    {
                        "id": "check",
                        "provider": "local_deterministic",
                        "input": "ok",
                        "fixture_dir": "fixture",
                        "contract": "contract.json",
                        "manifest": "manifest.json",
                        "expected_outcome": "passed",
                        "requires_human": True,
                    }
                ],
                fastpath=self._ack_fastpath(),
            ),
        )
        task = result["tasks"][0]
        self.assertNotEqual(task["actual_outcome"], "passed")
        self.assertFalse(task["fastpath_hit"])
        self.assertFalse(result["passed_deterministic"])

    def test_human_required_text_completion_falls_through(self) -> None:
        result = run_eval_suite(
            workspace=self.ws,
            suite=self._suite(
                [
                    {
                        "id": "human",
                        "provider": self.spy.name,
                        "judgment": "model",
                        "capability": "text_completion",
                        "input": "ok",
                        "requires_human": True,
                    }
                ],
                fastpath=self._ack_fastpath(),
            ),
        )
        self.assertEqual(self.spy.calls, 1)
        task = result["tasks"][0]
        self.assertFalse(task["fastpath_hit"])
        self.assertEqual(task["reason"], "unsafe_requires_human")
        self.assertFalse(result["passed_deterministic"])

        omitted = run_eval_suite(
            workspace=self.ws,
            suite=self._suite(
                [
                    {
                        "id": "human-default",
                        "provider": self.spy.name,
                        "capability": "text_completion",
                        "input": "ok",
                        "requires_human": True,
                    }
                ],
                fastpath=self._ack_fastpath(),
            ),
        )["tasks"][0]
        self.assertEqual(self.spy.calls, 2)
        self.assertFalse(omitted["fastpath_hit"])
        self.assertEqual(omitted["reason"], "unsafe_requires_human")
        self.assertNotEqual(omitted["actual_outcome"], "text_completed")

    def test_binding_preserves_one_pass_normalization(self) -> None:
        from runspecimen.fastpath import bind_fastpath_config

        doc = {
            "schema_kind": "fastpath_config",
            "schema_version": 1,
            "enabled": True,
            "rules": [
                {
                    "id": "ack",
                    "exact": ["ok! !"],
                    "outcome": {"type": "respond", "text": "yes"},
                }
            ],
        }
        compiled = parse_fastpath_config(doc)
        self.assertEqual(compiled["rules"][0]["exact"], ["ok! !"])
        before = complete_fastpath_request(workspace=self.ws, text="ok! !", config=compiled)
        self.assertTrue(before["fastpath_hit"])
        self.assertFalse(
            complete_fastpath_request(workspace=self.ws, text="ok", config=compiled)["fastpath_hit"]
        )
        bound = bind_fastpath_config(doc)
        self.assertEqual(bound["rules"][0]["exact"], ["ok! !"])
        reloaded = parse_fastpath_config(bound)
        self.assertEqual(reloaded["rules"][0]["exact"], ["ok! !"])
        after = complete_fastpath_request(workspace=self.ws, text="ok! !", config=reloaded)
        self.assertTrue(after["fastpath_hit"])
        introduced = complete_fastpath_request(workspace=self.ws, text="ok", config=reloaded)
        self.assertFalse(introduced["fastpath_hit"])

    def test_supplied_cost_is_kept_and_missing_usage_stays_unknown(self) -> None:
        class Metered:
            name = "metered"

            def run_task(self, *, workspace: Path, task: dict) -> dict:
                return {
                    "outcome": "model_ran",
                    "deterministic": False,
                    "llm_input_tokens": 11,
                    "llm_output_tokens": 7,
                    "llm_inference_cost": 0.012,
                }

        class UnknownUsage:
            name = "unknown_usage"

            def run_task(self, *, workspace: Path, task: dict) -> dict:
                return {"outcome": "model_ran", "deterministic": False, "actual_llm_cost": 0}

        register_eval_provider(Metered())
        register_eval_provider(UnknownUsage())
        measured = run_eval_suite(
            workspace=self.ws,
            suite=self._suite(
                [
                    {
                        "id": "cost",
                        "provider": "metered",
                        "judgment": "model",
                        "capability": "text_completion",
                        "input": "not a phrase",
                    }
                ],
                fastpath=self._ack_fastpath(),
            ),
        )["tasks"][0]
        self.assertEqual(measured["reason"], "no_match")
        self.assertEqual(measured["llm_inference_cost"], 0.012)
        self.assertEqual(measured["actual_llm_cost"], 0.012)
        self.assertEqual(measured["llm_input_tokens"], 11)
        self.assertEqual(measured["actual_llm_tokens_used"], 18)

        unknown = run_eval_suite(
            workspace=self.ws,
            suite=self._suite(
                [{"id": "unk", "provider": "unknown_usage", "input": "ok"}]
            ),
        )["tasks"][0]
        self.assertIsNone(unknown["llm_input_tokens"])
        self.assertIsNone(unknown["llm_output_tokens"])
        self.assertIsNone(unknown["actual_llm_tokens_used"])
        self.assertEqual(unknown["actual_llm_cost"], 0)
        self.assertEqual(unknown["llm_inference_cost"], 0)

    def test_eval_run_cli_enabled_disabled_and_digest_bound(self) -> None:
        from runspecimen.artifact import bind_artifact_digest

        def invoke(doc: dict) -> subprocess.CompletedProcess[str]:
            path = self.ws / "cli-suite.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "runspecimen",
                    "eval",
                    "run",
                    "--workspace",
                    str(self.ws),
                    "--suite",
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(ROOT),
                env={**dict(**__import__("os").environ), "PYTHONPATH": str(SRC)},
            )

        task = {
            "id": "req",
            "provider": "local_deterministic",
            "input": "ok",
            "fixture_dir": "missing-fixture",
            "contract": "missing.json",
            "expected_outcome": "passed",
            "requires_human": True,
        }
        enabled = self._suite([task], fastpath=self._ack_fastpath())
        for _ in range(2):
            proc = invoke(enabled)
            self.assertNotIn("unknown field", proc.stderr)
            self.assertNotIn("index", proc.stderr)
            body = json.loads(proc.stdout)
            self.assertEqual(body["result"]["tasks"][0]["actual_outcome"], "failed")
            self.assertFalse(body["result"]["passed_deterministic"])

        disabled = self._suite([task], fastpath={"enabled": False, "rules": []})
        proc = invoke(disabled)
        self.assertNotIn("unknown field", proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["result"]["tasks"][0]["actual_outcome"], "failed")

        bound = bind_artifact_digest(json.loads(json.dumps(enabled)))
        proc = invoke(bound)
        self.assertNotIn("artifact_digest mismatch", proc.stderr)
        self.assertNotIn("unknown field", proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["result"]["tasks"][0]["actual_outcome"], "failed")

    def test_dashboard_refresh_updates_fastpath_fields(self) -> None:
        import shutil

        node = shutil.which("node")
        self.assertIsNotNone(node, "node is required to execute renderStatus")
        from tests.helpers import base_contract, write_contract
        from runspecimen.dashboard import dashboard_document

        contract_path = write_contract(self.ws, "contract.json", base_contract())
        page = dashboard_document(
            workspace=self.ws.resolve(),
            contract_path=contract_path.resolve(),
            status={"phase": "none"},
        )
        script = page.split("<script>", 1)[1].split("</script>", 1)[0]
        helper = script[: script.index("function renderTrust")]
        render = script[script.index("function renderTrust") : script.index("let refreshing")]
        program = r"""
const store = {};
function make(id) {
  if (!store[id]) {
    store[id] = {
      id,
      textContent: "",
      className: "",
      dataset: {},
      hidden: false,
      classList: { remove() {}, add() {} },
      replaceChildren() {},
      append() {},
      querySelector() { return { textContent: "" }; },
    };
  }
  return store[id];
}
const document = {
  getElementById: make,
  body: { classList: { remove() {}, add() {} } },
  querySelectorAll: () => [],
};
const window = { matchMedia: () => ({ matches: true }) };
""" + helper + "\n" + render + r"""
function doc(executions, avoided, note) {
  return {
    phase: "none",
    view: {
      phase_label: "None",
      phase_tone: "idle",
      cards: { phase: ["None", "", "good"] },
      steps: [],
      warnings: [],
      next_action: "wait",
      certificate_id: "none",
      happened: "nothing",
      continue_label: "no",
      continue_detail: "no",
      continue_tone: "idle",
      run_identity: "c / r",
      trust_ladder: [],
      evidence: {
        check_outcome: "failed",
        applicability: "stale",
        fastpath_executions: executions,
        model_calls_avoided: avoided,
        note: "panel",
        fastpath_note: note,
      },
    },
  };
}
renderStatus(doc(1, 0, "first"));
if (store["ev-fastpath"].textContent !== "1") process.exit(2);
if (store["ev-avoided"].textContent !== "0") process.exit(3);
if (store["ev-fastpath-note"].textContent !== "first") process.exit(4);
renderStatus(doc(4, 2, "second"));
if (store["ev-fastpath"].textContent !== "4") process.exit(5);
if (store["ev-avoided"].textContent !== "2") process.exit(6);
if (store["ev-fastpath-note"].textContent !== "second") process.exit(7);
if (store["ev-outcome"].textContent !== "failed") process.exit(8);
"""
        proc = subprocess.run(
            [node, "-e", program],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main()
