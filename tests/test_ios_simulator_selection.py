import importlib.util
import json
from pathlib import Path
from unittest import mock
import unittest


class SimulatorSelectionTests(unittest.TestCase):
    def module(self):
        path = Path(__file__).resolve().parents[1] / "apps/ios/Scripts/select_ios_simulator.py"
        spec = importlib.util.spec_from_file_location("sim_selector", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def selector(self):
        return self.module().select

    def test_selects_sdk_runtime_not_first_phone(self):
        devices = {
            "devices": {
                "com.apple.CoreSimulator.SimRuntime.iOS-26-4": [
                    {"name": "iPhone", "isAvailable": True, "udid": "old"}
                ],
                "com.apple.CoreSimulator.SimRuntime.iOS-26-5": [
                    {"name": "iPhone", "isAvailable": True, "udid": "matching"}
                ],
            }
        }
        self.assertEqual(self.selector()(devices, "26.5"), "matching")

    def test_missing_matching_runtime_fails_instead_of_falling_back(self):
        with self.assertRaisesRegex(ValueError, "SDK"):
            self.selector()(
                {
                    "devices": {
                        "com.apple.CoreSimulator.SimRuntime.iOS-27-0": [
                            {"name": "iPhone", "isAvailable": True, "udid": "wrong"}
                        ]
                    }
                },
                "27.1",
            )

    def test_runtime_identifier_matches_sdk_not_first_runtime(self):
        runtimes = {
            "runtimes": [
                {
                    "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-4",
                    "isAvailable": True,
                },
                {
                    "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
                    "isAvailable": True,
                },
            ]
        }
        self.assertEqual(
            self.module().runtime_identifier(runtimes, "26.5"),
            "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
        )

    def test_missing_runtime_fails_instead_of_falling_back(self):
        with self.assertRaisesRegex(ValueError, "SDK"):
            self.module().runtime_identifier(
                {
                    "runtimes": [
                        {
                            "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-27-0",
                            "isAvailable": True,
                        }
                    ]
                },
                "27.1",
            )

    def test_iphone_devicetype_returns_first_iphone(self):
        self.assertEqual(
            self.module().iphone_devicetype(
                {
                    "devicetypes": [
                        {
                            "name": "iPad Pro 11-inch",
                            "identifier": "com.apple.CoreSimulator.SimDeviceType.iPad-Pro-11",
                        },
                        {
                            "name": "iPhone 16",
                            "identifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-16",
                        },
                    ]
                }
            ),
            "com.apple.CoreSimulator.SimDeviceType.iPhone-16",
        )

    def test_iphone_devicetype_fails_without_iphone(self):
        with self.assertRaisesRegex(ValueError, "iPhone"):
            self.module().iphone_devicetype(
                {
                    "devicetypes": [
                        {
                            "name": "iPad Pro 11-inch",
                            "identifier": "com.apple.CoreSimulator.SimDeviceType.iPad-Pro-11",
                        }
                    ]
                }
            )

    def test_create_uses_runtimes_and_devicetypes_not_device_catalog(self):
        module = self.module()
        calls = []

        def fake_check_output(cmd, text=True):
            calls.append(list(cmd))
            if cmd[2:5] == ["list", "runtimes", "-j"]:
                return json.dumps(
                    {
                        "runtimes": [
                            {
                                "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
                                "isAvailable": True,
                            }
                        ]
                    }
                )
            if cmd[2:5] == ["list", "devicetypes", "-j"]:
                return json.dumps(
                    {
                        "devicetypes": [
                            {
                                "name": "iPhone 16",
                                "identifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-16",
                            }
                        ]
                    }
                )
            if cmd[2:4] == ["create", module.CREATED_NAME]:
                return "NEW-UDID\n"
            raise AssertionError(cmd)

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            return mock.Mock(returncode=0)

        with mock.patch.object(module.subprocess, "check_output", fake_check_output):
            with mock.patch.object(module.subprocess, "run", fake_run):
                self.assertEqual(module.create("26.5"), "NEW-UDID")

        joined = [" ".join(cmd) for cmd in calls]
        self.assertTrue(any("list runtimes -j" in line for line in joined))
        self.assertTrue(any("list devicetypes -j" in line for line in joined))
        self.assertFalse(any("list devices" in line for line in joined))
        self.assertTrue(any(f"create {module.CREATED_NAME}" in line for line in joined))
        self.assertTrue(any(f"delete {module.CREATED_NAME}" in line for line in joined))
