import ast
from pathlib import Path
import importlib.util
import types
import unittest

root=Path(__file__).resolve().parents[1]
path=root/'anki-global-addon'/'zotero_global_capture'/'__init__.py'
tree=ast.parse(path.read_text(encoding='utf8'))
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('add_review_to_toolbar','open_kyle_book')]
spec=importlib.util.spec_from_file_location('review_logic',root/'anki-global-addon'/'zotero_global_capture'/'review_logic.py')
logic=importlib.util.module_from_spec(spec);spec.loader.exec_module(logic)

class ShortcutTests(unittest.TestCase):
 def test_two_entries_select_separately_and_do_not_interrupt_a_card(self):
  saved=[];shown=[];messages=[];queries=[]
  review=types.SimpleNamespace(dialog=None,busy=False,show_next=lambda manual:shown.append(manual))
  env={'mw':types.SimpleNamespace(col=types.SimpleNamespace(find_cards=lambda q:queries.append(q) or [1])),
       'controller':types.SimpleNamespace(review=review),'settings':lambda:{'model':'Words','review_book':''},
       'save_settings':lambda cfg:saved.append(dict(cfg)), 'show_feedback':messages.append,
       'BOOK_TAGS':{'cet4_kyle':'zvr_kyle_cet4','cet6_kyle':'zvr_kyle_cet6'}, 'open_review_from_toolbar':lambda:None,
       'scope_label':logic.scope_label}
  exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env)
  links=[];toolbar=types.SimpleNamespace(create_link=lambda name,label,callback,**kw:(name,label,callback,kw))
  env['add_review_to_toolbar'](links,toolbar)
  self.assertEqual([x[1] for x in links],['开始学习','四级范围','六级范围'])
  # The main-screen button must say which scope it is about to study.
  self.assertIn('所选牌组',links[0][3]['tip'])
  links[1][2]();links[2][2]()
  # The book buttons now write the same deck+tag scope as the settings dialog instead of
  # the old parallel 词书 key, and they scope by tag across all decks.
  self.assertEqual([x['review_book'] for x in saved],['',''])
  self.assertEqual([x['review_scope_decks'] for x in saved],[[],[]])
  self.assertEqual([x['review_scope_tags'] for x in saved],[['zvr_kyle_cet4'],['zvr_kyle_cet6']])
  self.assertEqual([x['review_scope_name'] for x in saved],['四级词汇','六级词汇'])
  self.assertIn('tag:zvr_kyle_cet4',queries[0]);self.assertIn('tag:zvr_kyle_cet6',queries[1])
  review.dialog=object();links[1][2]();self.assertEqual(len(saved),2);self.assertEqual(shown,[True,True])

 def test_start_button_names_the_saved_scope(self):
  # Anki's main screen must not leave the user guessing which scope will pop next.
  cfg={'model':'Words','review_scope_name':'四级 + 六级','review_scope_decks':[],'review_scope_tags':[]}
  env={'mw':types.SimpleNamespace(col=None),'settings':lambda:cfg,'scope_label':logic.scope_label,
       'controller':types.SimpleNamespace(review=types.SimpleNamespace(dialog=None,busy=False)),
       'open_review_from_toolbar':lambda:None,'show_feedback':lambda *_a,**_k:None,'BOOK_TAGS':{}}
  exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env)
  links=[];env['add_review_to_toolbar'](links,types.SimpleNamespace(create_link=lambda name,label,callback,**kw:(name,label,callback,kw)))
  self.assertIn('四级 + 六级',links[0][3]['tip'])
if __name__=='__main__':unittest.main()
