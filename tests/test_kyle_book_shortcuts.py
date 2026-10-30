import ast
from pathlib import Path
import types
import unittest

path=Path(__file__).resolve().parents[1]/'anki-global-addon'/'zotero_global_capture'/'__init__.py'
tree=ast.parse(path.read_text(encoding='utf8'))
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('add_review_to_toolbar','open_kyle_book')]

class ShortcutTests(unittest.TestCase):
 def test_two_entries_select_separately_and_do_not_interrupt_a_card(self):
  saved=[];shown=[];messages=[];queries=[]
  review=types.SimpleNamespace(dialog=None,busy=False,show_next=lambda manual:shown.append(manual))
  env={'mw':types.SimpleNamespace(col=types.SimpleNamespace(find_cards=lambda q:queries.append(q) or [1])),
       'controller':types.SimpleNamespace(review=review),'settings':lambda:{'model':'Words','review_book':''},
       'save_settings':lambda cfg:saved.append(dict(cfg)), 'show_feedback':messages.append,
       'BOOK_TAGS':{'cet4_kyle':'zvr_kyle_cet4','cet6_kyle':'zvr_kyle_cet6'}, 'open_review_from_toolbar':lambda:None}
  exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env)
  links=[];toolbar=types.SimpleNamespace(create_link=lambda name,label,callback,**kw:(name,label,callback))
  env['add_review_to_toolbar'](links,toolbar)
  self.assertEqual([x[1] for x in links],['单词复习','四级词书','六级词书'])
  links[1][2]();links[2][2]()
  # The book buttons now write the same deck+tag scope as the settings dialog instead of
  # the old parallel 词书 key, and they scope by tag across all decks.
  self.assertEqual([x['review_book'] for x in saved],['',''])
  self.assertEqual([x['review_scope_decks'] for x in saved],[[],[]])
  self.assertEqual([x['review_scope_tags'] for x in saved],[['zvr_kyle_cet4'],['zvr_kyle_cet6']])
  self.assertEqual([x['review_scope_name'] for x in saved],['四级词书','六级词书'])
  self.assertIn('tag:zvr_kyle_cet4',queries[0]);self.assertIn('tag:zvr_kyle_cet6',queries[1])
  review.dialog=object();links[1][2]();self.assertEqual(len(saved),2);self.assertEqual(shown,[True,True])
if __name__=='__main__':unittest.main()
