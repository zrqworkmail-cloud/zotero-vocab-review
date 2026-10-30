import importlib
from pathlib import Path
import sys,types,unittest
root=Path(__file__).resolve().parents[1]/'anki-global-addon'/'zotero_global_capture'
pkg=types.ModuleType('kyle_enrich_test');pkg.__path__=[str(root)];sys.modules[pkg.__name__]=pkg
m=importlib.import_module('kyle_enrich_test.kyle_enrich')
class EnrichmentTests(unittest.TestCase):
 def test_only_fills_blank_fields_and_requires_real_exam_source(self):
  fields={'正面':{'value':'predict'},'解释':{'value':'existing'},'音标':{'value':'existing phone'},'词根':{'value':''},'权威例句':{'value':''},'例句':{'value':''}}
  sources={'predict':[{'ukphone':'x','sentence':{'sentences':[{'sContent':'I predict rain.','sCn':'我预测会下雨。'}]},'realExamSentence':{'sentences':[{'sContent':'Unsupported.'},{'sContent':'We predict it.','sourceInfo':{'level':'CET6','year':'2021.06','paper':'第一套'}}]}}]}
  result=m.planned_updates([{'noteId':1,'fields':fields}],sources,'正面')
  self.assertEqual(len(result),1);v=result[0]['fields'];self.assertNotIn('解释',v);self.assertNotIn('音标',v);self.assertIn('CET6 2021.06 第一套',v['权威例句']);self.assertNotIn('Unsupported',v['权威例句']);self.assertIn('pre + dict',v['词根']);self.assertEqual(result[0]['before']['词根'],'')
 def test_adds_additional_senses_only_to_unchanged_imported_notes(self):
  sources={'apple':[{'trans':[{'pos':'n','tranCn':'苹果'}]}, {'trans':[{'pos':'n','tranCn':'苹果'},{'pos':'n','tranCn':'苹果树'}]}]}
  def note(value):return {'noteId':1,'fields':{'正面':{'value':'apple'},'解释':{'value':value}}}
  added=m.planned_updates([note('n. 苹果')],sources,'正面',[1])[0]
  self.assertIn('苹果树',added['fields']['解释']);self.assertEqual(added['before']['解释'],'n. 苹果')
  self.assertFalse(m.planned_updates([note('自定义解释')],sources,'正面',[1]))
  self.assertFalse(m.planned_updates([note('n. 苹果')],sources,'正面',[]))
if __name__=='__main__':unittest.main()
