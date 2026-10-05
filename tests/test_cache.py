import contextlib,hashlib,importlib.util,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('apkm',Path(__file__).resolve().parents[1]/'src/apkm.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class CacheTests(unittest.TestCase):
 def fixture(self,root):
  p=dict(name='test',package_id='org.example.test',version_code=1,version_name='1',min_sdk=21,abis=['any'],sha256='a'*64,size=10,url='app.apk')
  m.write_json(root/'sources.json',{'f':dict(type='fdroid',url='https://example.org/repo',keyring='key.gpg')})
  m.write_json(root/'indexes/f.json',dict(schema_version=1,revision=100,packages=[p]))
  return p
 def test_search_info_legacy_cache_no_network(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.fixture(root)
   with patch.object(m,'CONFIG',root),patch.object(m,'fetch',side_effect=AssertionError('unexpected network')),patch.object(m,'refresh',side_effect=AssertionError('unexpected refresh')),contextlib.redirect_stdout(io.StringIO()) as out:
    for command in [['search','test'],['info','test']]:self.assertEqual(m.main(command),0)
   self.assertIn('本地索引',out.getvalue());self.assertIn('test',out.getvalue())
 def test_missing_cache_guidance_no_network(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.fixture(root);(root/'indexes/f.json').unlink()
   with patch.object(m,'CONFIG',root),patch.object(m,'fetch',side_effect=AssertionError('network')),contextlib.redirect_stderr(io.StringIO()) as out:
    self.assertEqual(m.main(['search','test']),2)
   self.assertIn('apkm update f',out.getvalue())
 def test_apk_reuse_and_corrupt_cache_redownload(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=self.fixture(root);p['source_url']='https://example.org/repo'
   b=io.BytesIO()
   with zipfile.ZipFile(b,'w') as z:z.writestr('AndroidManifest.xml',b'test')
   data=b.getvalue();p.update(size=len(data),sha256=hashlib.sha256(data).hexdigest())
   args=m.parser('apkm').parse_args(['install','--download-only','--output-dir',d,'test']);out=m.Output(args)
   final=root/f'test-1-{p["sha256"][:12]}.apk';final.write_bytes(data)
   with patch.object(m.urllib.request,'build_opener',side_effect=AssertionError('network')):self.assertEqual(m.download(p,args,out),final)
   final.write_bytes(b'x'*len(data))
   with patch.object(m.urllib.request,'build_opener') as opener:
    opener.return_value.open.return_value=io.BytesIO(data);self.assertEqual(m.download(p,args,out),final)
   self.assertEqual(final.read_bytes(),data)
 def test_mirror_failure_preserves_source(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.fixture(root);before=(root/'sources.json').read_bytes()
   with patch.object(m,'CONFIG',root),patch.object(m,'refresh',side_effect=m.Failure('bad signature',4)),contextlib.redirect_stderr(io.StringIO()):self.assertEqual(m.main(['source','set-url','f','https://mirror.example.org/repo']),4)
   self.assertEqual((root/'sources.json').read_bytes(),before)
 def test_update_selected_source_only(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.fixture(root)
   with patch.object(m,'CONFIG',root),patch.object(m,'refresh') as refresh:
    self.assertEqual(m.main(['update','f']),0);self.assertEqual(refresh.call_count,1);self.assertEqual(refresh.call_args.args[0],'f')
if __name__=='__main__':unittest.main()
