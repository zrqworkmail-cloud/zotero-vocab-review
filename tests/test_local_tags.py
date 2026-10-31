"""The tag list must come from Anki's own tag API.

The first version read `select name from tags` inside a try/except that returned an
empty list. Anki's tags table has no `name` column, so the query always raised, the
exception was swallowed, and the settings dialog showed nobody any tags while looking
like it had simply found none. A fake collection shaped like the real one is what
catches that; a fake that only has whatever method the code happens to call does not.
"""
import ast
import importlib.util
import sqlite3
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
path = ROOT / '__init__.py'
tree = ast.parse(path.read_text(encoding='utf-8'))
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'local_tags')
module = ast.Module(body=[node], type_ignores=[])


def run_with(mw):
    logs = []
    scope = {'mw': mw, 'log_runtime': logs.append}
    exec(compile(module, str(path), 'exec'), scope)
    return scope['local_tags'](), logs


class AnkiShapedCollection:
    """A sqlite tags table with Anki's real columns, not the ones the code assumed."""

    def __init__(self, names):
        self.connection = sqlite3.connect(':memory:')
        self.connection.execute('create table tags (id integer primary key, n text, m text, usn integer, lw integer)')
        for index, name in enumerate(names):
            self.connection.execute('insert into tags (id, n, m, usn, lw) values (?, ?, 0, -1, 0)', (index, name))
        self.db = types.SimpleNamespace(
            all=lambda query, *args: self.connection.execute(query, args).fetchall())
        self.tags = types.SimpleNamespace(all=lambda: list(names))


class LocalTags(unittest.TestCase):
    def test_reads_registered_tags_through_anki(self):
        value, logs = run_with(types.SimpleNamespace(col=AnkiShapedCollection(['zvr_kyle_cet4', 'zotero'])))
        self.assertEqual(value, ['zotero', 'zvr_kyle_cet4'])
        self.assertEqual(logs, [], 'a working read must not log a failure: %s' % logs)

    def test_a_sql_column_guess_would_have_failed_loudly(self):
        # Guards the shape of the fake above: if `select name from tags` ever starts
        # working here, this test is no longer proving anything.
        with self.assertRaises(sqlite3.OperationalError):
            AnkiShapedCollection(['x']).db.all('select name from tags')

    def test_failure_is_reported_as_none_not_as_no_tags(self):
        value, logs = run_with(types.SimpleNamespace(col=None))
        self.assertIsNone(value, 'None means "could not read"; [] means "account has no tags"')
        self.assertTrue(logs and 'tag list unavailable' in logs[0], logs)

    def test_no_collection_at_all_does_not_raise(self):
        # The settings dialog opens before a profile finishes loading sometimes.
        value, logs = run_with(types.SimpleNamespace(col=None))
        self.assertIsNone(value)


if __name__ == '__main__':
    unittest.main()
