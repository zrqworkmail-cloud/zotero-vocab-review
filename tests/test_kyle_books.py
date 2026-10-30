import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture'
pkg = types.ModuleType('kyle_test_pkg'); pkg.__path__ = [str(ROOT)]; sys.modules[pkg.__name__] = pkg
books = importlib.import_module('kyle_test_pkg.kyle_books')
logic = importlib.import_module('kyle_test_pkg.review_logic')

class ImportTests(unittest.TestCase):
    def test_reuses_existing_and_imports_missing_once_with_both_tags(self):
        with tempfile.TemporaryDirectory() as directory:
            def row(word):
                return {'headWord': word, 'content': {'word': {'content': {'trans': [{'pos':'n','tranCn':'释义'}], 'sentence': {'sentences':[{'sContent':'A sentence.', 'sCn':'句子。'}]}}}}}
            p = Path(directory)
            (p / '四级-完整.jsonl').write_text('\n'.join(json.dumps(row(x), ensure_ascii=False) for x in ['apple','banana','apple']), encoding='utf8')
            (p / '六级-完整.jsonl').write_text('\n'.join(json.dumps(row(x), ensure_ascii=False) for x in ['apple','cherry']), encoding='utf8')
            notes = [{'noteId':1, 'fields':{'Front':{'value':'apple'}}, 'tags':['existing']}]
            def api(action, params):
                if action == 'getActiveProfile': return 'p'
                if action == 'modelFieldNames': return ['Front','Back','例句']
                if action == 'findNotes': return [n['noteId'] for n in notes]
                if action == 'notesInfo': return [n for n in notes if n['noteId'] in params['notes']]
                if action == 'addTags':
                    for n in notes:
                        if n['noteId'] in params['notes']: n['tags'].append(params['tags'])
                    return None
                if action == 'createDeck': return 1
                if action == 'addNotes':
                    added=[]
                    for n in params['notes']:
                        item={'noteId':len(notes)+1,'fields':{k:{'value':v} for k,v in n['fields'].items()},'tags':n['tags'][:]}
                        notes.append(item);added.append(item['noteId'])
                    return added
                raise AssertionError(action)
            cfg={'model':'Words','front_field':'Front','back_field':'Back'}
            first=books.import_books(api,cfg,p,p/'journal.jsonl')
            self.assertEqual((first['unique'],first['reused'],first['added']), (3,1,2))
            self.assertEqual(set(notes[0]['tags']), {'existing','zvr_kyle_cet4','zvr_kyle_cet6'})
            self.assertIn('句子。',notes[1]['fields']['例句']['value'])
            second=books.import_books(api,cfg,p,p/'journal.jsonl')
            self.assertEqual((second['reused'],second['added']), (3,0))
            self.assertIn('tag:"zvr_kyle_cet4"', logic._search(dict(cfg, deck='X', review_book='cet4_kyle')))
            self.assertIn('tag:"zvr_kyle_cet6"', logic._search(dict(cfg, deck='X', review_book='cet6_kyle')))

if __name__ == '__main__': unittest.main()
