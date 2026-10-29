"""Installed Node dependencies must not enter the offline source snapshot."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_check_source',ROOT/'scripts/release_check.py')
release=importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
class ReleaseSourceDependenciesTests(unittest.TestCase):
    def test_node_modules_are_excluded_but_plugin_sources_are_staged(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'source'
            plugin=root/'plugins/runspecimen/dsh'
            (plugin/'lib').mkdir(parents=True)
            (plugin/'lib/index.js').write_text('export {};')
            (plugin/'node_modules/.bin').mkdir(parents=True)
            (plugin/'node_modules/.bin/tool').symlink_to('../tool/main.js')
            destination=Path(directory)/'staged'
            with patch.object(release,'ROOT',root),patch.object(release,'SOURCE_COMPONENTS',('plugins',)):
                release.stage_source(destination)
            self.assertTrue((destination/'plugins/runspecimen/dsh/lib/index.js').is_file())
            self.assertFalse((destination/'plugins/runspecimen/dsh/node_modules').exists())
