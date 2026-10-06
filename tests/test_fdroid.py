import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('apkm',Path(__file__).resolve().parents[1]/'src/apkm.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class FDroidTests(unittest.TestCase):
 def fixture(self):
  def v(code,sdk,abi):return dict(versionCode=code,versionName=str(code),minSdkVersion=sdk,nativecode=[abi],hashType='sha256',hash='a'*64,size=100,apkName=f'app_{code}.apk')
  return dict(repo=dict(timestamp=100),apps=[dict(packageName='org.example.app',suggestedVersionCode='2',localized={'en-US':{'name':'Example','summary':'Test'}})],packages={'org.example.app':[v(3,21,'arm64-v8a'),v(2,30,'arm64-v8a'),v(1,21,'x86_64')]})
 def test_stable_and_device_variants(self):
  p=m.normalize_fdroid(self.fixture())['packages'][0];p['source_url']='https://example.org/repo/'
  self.assertEqual(p['version_code'],2);self.assertEqual(p['min_sdk'],30)
  self.assertIn('Example',p['description'])
  self.assertEqual(m.select_variant(p,25,['x86_64'])['version_code'],1)
  with self.assertRaises(m.Failure):m.select_variant(p,25,['arm64-v8a'])
 def test_unsigned_or_rollback_cannot_replace_cache(self):
  for code,timestamp in [(1,101),(0,99)]:
   with tempfile.TemporaryDirectory() as d:
    root=Path(d);key=root/'key';key.touch();target=root/'indexes/f.json';target.parent.mkdir();target.write_text('{"revision":100}')
    data=self.fixture();data['repo']['timestamp']=timestamp
    with patch.object(m,'CONFIG',root),patch.object(m,'fetch',side_effect=[json.dumps(data).encode(),b'sig']),patch.object(m,'run',return_value=subprocess.CompletedProcess([],code,'','')):
     with self.assertRaises(m.Failure):m.refresh('f',dict(type='fdroid',url='https://example.org',keyring=str(key)),m.Output(m.parser('apkm').parse_args(['update'])))
    self.assertEqual(target.read_text(),'{"revision":100}')
 def test_mixed_abi_metadata_preserves_supported_variants(self):
  data=self.fixture();data['packages']['org.example.app'][1]['nativecode']=['arm64-v8a','armeabi','mips','x86_64/darwin']
  p=m.normalize_fdroid(data)['packages'][0]
  self.assertEqual(p['version_code'],2);self.assertEqual(p['abis'],['arm64-v8a'])
  data['packages']['org.example.app'][1]['nativecode']=['mips']
  self.assertEqual(m.normalize_fdroid(data)['packages'][0]['version_code'],1)
 def test_third_party_requires_explicit_key(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m,'CONFIG',Path(d)):
   self.assertEqual(m.main(['source','add','f','https://example.org/repo','--type','fdroid']),2)
if __name__=='__main__':unittest.main()
