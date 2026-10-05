import contextlib, hashlib, importlib.util, io, json, os, subprocess, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('apkm',Path(__file__).resolve().parents[1]/'src/apkm.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def args(self,*a):return m.parser('apkm').parse_args(list(a))
 def test_urls(self):
  with self.assertRaises(m.Failure):m.validate_url('http://host/app.apk')
  self.assertEqual(m.validate_url('https://host/app.apk'),'https://host/app.apk')
 def test_manifest_required(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.apk'
   with zipfile.ZipFile(p,'w') as z:z.writestr('readme','no')
   with self.assertRaises(m.Failure):m.check_apk(p)
 def test_linux_root_not_android_root(self):
  args=self.args('--mode','root','doctor')
  with patch.object(m.Path,'is_file',return_value=False),patch.object(m.shutil,'which',return_value=None):
   with self.assertRaises(m.Failure) as e:m.Backend(args,m.Output(args))
   self.assertEqual(e.exception.code,3)
 def test_multiple_devices(self):
  args=self.args('doctor')
  result=subprocess.CompletedProcess([],0,'List of devices attached\na\tdevice\nb\tdevice\n','')
  with patch.object(m.shutil,'which',return_value='/bin/adb'),patch.object(m,'run',return_value=result):
   with self.assertRaises(m.Failure):m.Backend(args,m.Output(args))
 def test_install_failure_with_zero_exit(self):
  args=self.args('--mode','adb','doctor')
  devices=subprocess.CompletedProcess([],0,'List of devices attached\na\tdevice\n','')
  with patch.object(m.shutil,'which',return_value='/bin/adb'),patch.object(m,'run',return_value=devices):backend=m.Backend(args,m.Output(args))
  result=subprocess.CompletedProcess([],0,'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]','')
  with patch.object(m,'run',return_value=result):
   with self.assertRaises(m.Failure) as e:backend.install(Path('x.apk'))
   self.assertEqual(e.exception.code,5)
 def test_checksum_failure_leaves_no_apk(self):
  with tempfile.TemporaryDirectory() as d:
   data=b'bad';p={'source_url':'https://host/','url':'app.apk','name':'app','version_code':1,'size':3,'sha256':'0'*64}
   args=self.args('install','--download-only','--output-dir',d,'app')
   response=io.BytesIO(data)
   with patch.object(m.urllib.request,'build_opener') as opener:
    opener.return_value.open.return_value=response
    with self.assertRaises(m.Failure):m.download(p,args,m.Output(args))
   self.assertEqual(list(Path(d).iterdir()),[])
 def test_bad_signature_does_not_change_cache(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);key=root/'key.gpg';key.write_bytes(b'key')
   old=root/'indexes/test.json';old.parent.mkdir();old.write_text('{"revision": 9}')
   args=self.args('update')
   with patch.object(m,'CONFIG',root),patch.object(m,'fetch',side_effect=[b'{"schema_version":1,"packages":[]}',b'bad']),patch.object(m,'run',return_value=subprocess.CompletedProcess([],1,'','bad')):
    with self.assertRaises(m.Failure):m.refresh('test',{'url':'https://host/','keyring':str(key)},m.Output(args))
   self.assertEqual(old.read_text(),'{"revision": 9}')
 def test_revision_rollback(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);key=root/'key.gpg';key.write_bytes(b'key')
   old=root/'indexes/test.json';old.parent.mkdir();old.write_text('{"revision": 9}')
   args=self.args('update');new=json.dumps({'schema_version':1,'revision':8,'packages':[]}).encode()
   with patch.object(m,'CONFIG',root),patch.object(m,'fetch',side_effect=[new,b'sig']),patch.object(m,'run',return_value=subprocess.CompletedProcess([],0,'','')):
    with self.assertRaises(m.Failure):m.refresh('test',{'url':'https://host/','keyring':str(key)},m.Output(args))
 def test_help(self):
  for prog in ['apkm','apkg']:
   with contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaises(SystemExit) as e:m.parser(prog).parse_args(['--help'])
   self.assertEqual(e.exception.code,0)
if __name__=='__main__':unittest.main()
