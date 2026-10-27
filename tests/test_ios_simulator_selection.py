import importlib.util
from pathlib import Path
import unittest

class SimulatorSelectionTests(unittest.TestCase):
    def selector(self):
        path=Path(__file__).resolve().parents[1]/'apps/ios/Scripts/select_ios_simulator.py'
        spec=importlib.util.spec_from_file_location('sim_selector',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.select

    def test_selects_sdk_runtime_not_first_phone(self):
        devices={'devices':{'com.apple.CoreSimulator.SimRuntime.iOS-26-4':[{'name':'iPhone','isAvailable':True,'udid':'old'}], 'com.apple.CoreSimulator.SimRuntime.iOS-26-5':[{'name':'iPhone','isAvailable':True,'udid':'matching'}]}}
        self.assertEqual(self.selector()(devices,'26.5'),'matching')

    def test_missing_matching_runtime_fails_instead_of_falling_back(self):
        with self.assertRaisesRegex(ValueError,'SDK'):
            self.selector()({'devices':{'com.apple.CoreSimulator.SimRuntime.iOS-27-0':[{'name':'iPhone','isAvailable':True,'udid':'wrong'}]}},'27.1')
