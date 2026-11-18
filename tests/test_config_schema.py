import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'config_schema.py'
spec = importlib.util.spec_from_file_location('config_schema_test', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigMigrationTests(unittest.TestCase):
    def test_defaults_are_merged_and_version_is_stamped(self):
        value = module.migrate({'review_auto_example': True}, {'review_enabled': True})
        self.assertTrue(value['review_enabled'])
        self.assertEqual(value['review_auto_example_mode'], 'example')
        self.assertEqual(value['config_version'], module.CURRENT_CONFIG_VERSION)

    def test_explicit_new_value_wins_over_legacy_boolean(self):
        value = module.migrate({'review_auto_example': True,
                                'review_auto_example_mode': 'first'}, {})
        self.assertEqual(value['review_auto_example_mode'], 'first')

    def test_migration_is_idempotent(self):
        once = module.migrate({'review_auto_example': True}, {})
        twice = module.migrate(once, {})
        self.assertEqual(once, twice)


if __name__ == '__main__':
    unittest.main()
