import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
pkg = types.ModuleType('cet6_test_pkg'); pkg.__path__ = [str(ROOT)]; sys.modules[pkg.__name__] = pkg
spec = importlib.util.spec_from_file_location('cet6_test_pkg.cet6_books', ROOT / 'cet6_books.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

class BooksTest(unittest.TestCase):
    def test_existing_notes_are_tagged_once_missing_added_without_duplicate(self):
        old = module.books
        module.books = lambda: ([['apple', '', '苹果'], ['banana', '', '香蕉']], {'cet6':['apple','extra'], 'dictionary':{'extra':{'meaning':'额外'}}})
        notes = [{'noteId': 1, 'fields': {'Front': {'value': 'apple'}}, 'tags': []}]
        actions = []
        def api(action, params):
            actions.append((action, params))
            if action == 'getActiveProfile': return 'profile'
            if action == 'modelFieldNames': return ['Front','Back']
            if action == 'findNotes': return [n['noteId'] for n in notes]
            if action == 'notesInfo': return notes
            if action == 'addTags':
                for n in notes:
                    if n['noteId'] in params['notes']: n['tags'].append(params['tags'])
                return None
            if action == 'createDeck': return 1
            if action == 'addNotes':
                for n in params['notes']:
                    notes.append({'noteId':len(notes)+1, 'fields': {'Front': {'value':n['fields']['Front']}}, 'tags':n['tags']})
                return [n['noteId'] for n in notes[-len(params['notes']):]]
            raise AssertionError(action)
        try:
            cfg={'model':'Words','front_field':'Front','back_field':'Back'}
            r=module.setup_books(api,cfg)
            self.assertEqual((r['existing_full'],r['existing_core'],r['added']), (1,1,2))
            self.assertEqual(set(notes[0]['tags']), {'zvr_cet6_full','zvr_cet6_core'})
            self.assertEqual(module.setup_books(api,cfg)['added'],0)
        finally: module.books=old

    def test_profile_change_stops_tagging(self):
        old=module.books;module.books=lambda:([['apple','','苹果']],{'cet6':[],'dictionary':{}})
        profiles=iter(['a','b'])
        def api(action,params):
            if action=='getActiveProfile':return next(profiles)
            if action=='modelFieldNames':return ['Front','Back']
            if action=='findNotes':return [1]
            if action=='notesInfo':return [{'noteId':1,'fields':{'Front':{'value':'apple'}},'tags':[]}]
            raise AssertionError(action)
        try:
            with self.assertRaisesRegex(RuntimeError,'账户已切换'):
                module.setup_books(api,{'model':'Words','front_field':'Front','back_field':'Back'})
        finally:module.books=old

if __name__ == '__main__':unittest.main()
