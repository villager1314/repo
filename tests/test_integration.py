"""Exercise the actual apkg subprocess with a simulated authorized Android device."""
import contextlib, hashlib, importlib.util,io,json,os,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('apkm',ROOT/'src/apkm.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Integration(unittest.TestCase):
 def test_real_signed_index_and_tampering(self):
  with tempfile.TemporaryDirectory() as d:
   args=m.parser('apkm').parse_args(['update']);key=ROOT/'site/keys/apkm.gpg'
   index=(ROOT/'site/android/index.json').read_bytes();sig=(ROOT/'site/android/index.json.sig').read_bytes()
   source={'url':'https://example.invalid/android/','keyring':str(key)}
   with patch.object(m,'CONFIG',Path(d)),patch.object(m,'fetch',side_effect=[index,sig]):
    with contextlib.redirect_stdout(io.StringIO()):m.refresh('test',source,m.Output(args))
   before=(Path(d)/'indexes/test.json').read_bytes()
   with patch.object(m,'CONFIG',Path(d)),patch.object(m,'fetch',side_effect=[index+b' ',sig]):
    with self.assertRaises(m.Failure):m.refresh('test',source,m.Output(args))
   self.assertEqual((Path(d)/'indexes/test.json').read_bytes(),before)
 def test_download_install_and_version_confirmation(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);state=root/'state';bin=root/'bin';bin.mkdir()
   adb=bin/'adb'
   adb.write_text('''#!/usr/bin/env python3
import os,shlex,sys
from pathlib import Path
a=sys.argv[1:];state=Path(os.environ['FAKE_ANDROID_STATE'])
if a==['devices']:
 print('List of devices attached\\nFAKE\\tdevice');sys.exit(0)
assert a[:2]==['-s','FAKE'];a=a[2:]
if a[0]=='install':
 assert a[1]=='-r' and Path(a[2]).is_file()
 state.write_text('7');print('Performing Streamed Install\\nSuccess')
elif a[0]=='shell':
 a=shlex.split(a[1])
 if a==['getprop','ro.build.version.sdk']:print('35')
 elif a==['getprop','ro.product.cpu.abilist']:print('arm64-v8a,armeabi-v7a')
 elif a[:2]==['dumpsys','package']:
  if state.exists():print('versionCode='+state.read_text())
 elif a==['pm','list','packages']:
  if state.exists():print('package:com.example.test')
 else:sys.exit(9)
else:sys.exit(8)
''');adb.chmod(0o755)
   content=io.BytesIO()
   with zipfile.ZipFile(content,'w') as z:z.writestr('AndroidManifest.xml',b'test fixture, not a real APK')
   data=content.getvalue()
   package={'name':'testapp','package_id':'com.example.test','version_code':7,'version_name':'0.7','min_sdk':21,'abis':['arm64-v8a'],'url':'test.apk','source_url':'https://example.invalid/android/','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
   env={'PATH':str(bin)+os.pathsep+os.environ['PATH'],'FAKE_ANDROID_STATE':str(state),'XDG_CONFIG_HOME':str(root/'config'),'XDG_CACHE_HOME':str(root/'cache')}
   output=io.StringIO()
   with patch.dict(os.environ,env),patch.object(m,'CACHE',root/'cache'),patch.object(m,'catalog',return_value={'testapp':package}),patch.object(m.urllib.request,'build_opener') as opener,contextlib.redirect_stdout(output):
    opener.return_value.open.return_value=io.BytesIO(data)
    result=m.main(['--mode','adb','install','testapp'])
   self.assertEqual(result,0);self.assertEqual(state.read_text(),'7')
   self.assertIn('versionCode=7',output.getvalue());self.assertIn('安卓返回 Success',output.getvalue())
if __name__=='__main__':unittest.main()
