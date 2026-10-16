import contextlib,io,importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('apkm',Path(__file__).resolve().parents[1]/'src/apkm.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Names(unittest.TestCase):
 def setUp(self):
  self.p=dict(name='org.example.app',package_id='org.example.app',display_name='Example App',localized={'zh-CN':{'name':'示例应用','summary':'清理缓存'},'de':{'name':'Beispiel'}},description='English summary',version_code=1)
 def test_multilingual_search(self):
  for term in ['示例','example','Beispiel','缓存']:self.assertTrue(m.search_package(self.p,[term]))
  self.assertTrue(m.search_package(self.p,['示例','缓存']))
  self.assertFalse(m.search_package(self.p,['missing']))
 def test_name_only_and_exact(self):
  self.assertTrue(m.search_package(self.p,['示例'],True))
  self.assertFalse(m.search_package(self.p,['缓存'],True))
  self.assertTrue(m.search_package(self.p,['EXAMPLE  APP'],exact=True))
  self.assertFalse(m.search_package(self.p,['Example'],exact=True))
 def test_resolution_and_pinning(self):
  catalog={self.p['name']:self.p}
  for name in ['示例应用','ＥＸＡＭＰＬＥ App','org.example.app']:self.assertEqual(m.resolve_package(catalog,name),self.p)
  self.assertEqual(m.resolve_package(catalog,'示例应用=1')['version_code'],1)
  with self.assertRaises(m.Failure):m.resolve_package(catalog,'Example')
 def test_ambiguous_before_device_or_download(self):
  q=dict(self.p,name='org.other.app',package_id='org.other.app');catalog={self.p['name']:self.p,q['name']:q}
  with patch.object(m,'catalog',return_value=catalog),patch.object(m,'Backend',side_effect=AssertionError('no device')),patch.object(m,'download',side_effect=AssertionError('no download')),contextlib.redirect_stderr(io.StringIO()) as err:
   self.assertEqual(m.main(['install','示例应用']),2)
  self.assertIn('org.other.app',err.getvalue());self.assertEqual(m.resolve_package(catalog,'org.example.app'),self.p)
 def test_fdroid_metadata_retained(self):
  d={'repo':{'timestamp':1},'apps':[{'packageName':'org.example.app','name':'Example App','localized':self.p['localized'],'suggestedVersionCode':1}],'packages':{'org.example.app':[{'versionCode':1,'hashType':'sha256','hash':'a'*64,'apkName':'a.apk','size':1}]}}
  p=m.normalize_fdroid(d)['packages'][0]
  self.assertEqual(p['localized'],self.p['localized']);self.assertEqual(p['display_name'],'Example App');self.assertTrue(m.search_package(p,['缓存']))
