import contextlib,hashlib,importlib.util,io,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch,MagicMock
spec=importlib.util.spec_from_file_location('apkm',Path(__file__).resolve().parents[1]/'src/apkm.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class CleanupTests(unittest.TestCase):
 def scenario(self,case,keep=False,download_only=False):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);content=io.BytesIO()
   with zipfile.ZipFile(content,'w') as z:z.writestr('AndroidManifest.xml',b'test')
   data=content.getvalue();p=dict(name='app',package_id='org.example.app',version_code=7,version_name='7',min_sdk=21,abis=['any'],url='app.apk',source_url='https://example.org',size=len(data),sha256=hashlib.sha256(data).hexdigest())
   backend=MagicMock();backend.mode='root';backend.device_info.return_value=(35,['arm64-v8a']);backend.version.side_effect=[None,7 if case!='mismatch' else 6]
   call=['install','--output-dir',d,'app']+(['--keep-apk'] if keep else [])+(['--download-only'] if download_only else [])
   with patch.object(m,'catalog',return_value={'app':p}),patch.object(m,'Backend',return_value=backend),patch.object(m,'invoke_apkg',side_effect=m.Failure('install failed',5) if case=='failure' else None),patch.object(m.urllib.request,'build_opener') as opener,contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
    opener.return_value.open.return_value=io.BytesIO(data);code=m.main(call)
   exists=bool(list(root.glob('*.apk')))
   return code,exists
 def test_success_removes(self):self.assertEqual(self.scenario('success'),(0,False))
 def test_keep_apk(self):self.assertEqual(self.scenario('success',keep=True),(0,True))
 def test_failure_retains(self):self.assertEqual(self.scenario('failure'),(5,True))
 def test_version_mismatch_retains(self):self.assertEqual(self.scenario('mismatch'),(5,True))
 def test_download_only_retains(self):self.assertEqual(self.scenario('success',download_only=True),(0,True))
 def test_cleanup_error_does_not_report_install_failure(self):
  out=MagicMock()
  with patch.object(m.Path,'unlink',side_effect=PermissionError('test')):m.cleanup_apk(Path('x.apk'),out)
  self.assertEqual(out.event.call_args.args[0],'清理失败')
if __name__=='__main__':unittest.main()
