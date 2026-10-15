"""Archive parsing/selection, session cleanup and actual APKG subprocess behavior."""
import contextlib, hashlib, importlib.util,io,json,os,struct,subprocess,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('apkm',ROOT/'src/apkm.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def binary_manifest(split='',package='com.example.app',version='7'):
 strings=['manifest','package',package,m.ANDROID_NS,'versionCode','split',split]
 raw=b''; offsets=[]
 for s in strings:
  data=s.encode();offsets.append(len(raw));raw+=bytes([len(s),len(data)])+data+b'\0'
 start=28+4*len(strings);size=start+len(raw);padding=(-size)%4;size+=padding
 pool=struct.pack('<HHIIIIII',1,28,size,len(strings),0,0x100,start,0)+b''.join(struct.pack('<I',o) for o in offsets)+raw+b'\0'*padding
 attrs=[]
 for ns,name,val in [(0xffffffff,1,2),(3,4,None)]+([(0xffffffff,5,6)] if split else []):
  attrs.append(struct.pack('<IIIHBBI',ns,name,val if val is not None else 0xffffffff,8,0,3 if val is not None else 0x10,val if val is not None else int(version)))
 node=struct.pack('<HHIII',0x102,16,36+20*len(attrs),1,0xffffffff)+struct.pack('<IIHHHHHH',0xffffffff,0,20,20,len(attrs),0,0,0)+b''.join(attrs)
 return struct.pack('<HHI',3,8,8+len(pool)+len(node))+pool+node
def apk(split='',package='com.example.app',version='7',binary=True):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:
  data=binary_manifest(split,package,version) if binary else f'<manifest xmlns:android="{m.ANDROID_NS}" package="{package}" android:versionCode="{version}" split="{split}"><uses-sdk android:minSdkVersion="21"/></manifest>'.encode()
  z.writestr('AndroidManifest.xml',data)
 return b.getvalue()
class Archives(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.out=Mock();self.backend=Mock();self.backend.device_info.return_value=(35,['arm64-v8a','armeabi-v7a']);self.backend.version.return_value=7
 def tearDown(self):self.temp.cleanup()
 def archive(self,entries,name='app.apkm'):
  p=self.root/name
  with zipfile.ZipFile(p,'w') as z:
   for n,b in entries:z.writestr(n,b)
  return p
 def test_binary_manifest(self):
  p=self.root/'base.apk';p.write_bytes(apk());info=m.apk_metadata(p);self.assertEqual((info['package'],info['version'],info['split']),('com.example.app',7,''))
 def test_truncated_binary_manifest(self):
  with self.assertRaises(m.Failure):m.manifest_elements(binary_manifest()[:-1])
 def test_selection_and_temporary_cleanup(self):
  p=self.archive([('base.apk',apk()),('arm.apk',apk('config.arm64_v8a')),('x86.apk',apk('config.x86')),('en.apk',apk('config.en'))])
  m.install_archive(p,self.backend,self.out)
  paths=self.backend.install_set.call_args.args[0];self.assertEqual(len(paths),3);self.assertTrue(all(not p.exists() for p in paths));self.assertTrue(p.exists())
 def test_obb_is_not_extracted(self):
  p=self.archive([('base.apk',apk()),('Android/obb/com.example.app/main.7.com.example.app.obb',b'data')],'app.xapk')
  m.install_archive(p,self.backend,self.out);self.assertTrue(any(c.args[0]=='OBB 未安装' for c in self.out.event.call_args_list));self.assertEqual(len(self.backend.install_set.call_args.args[0]),1)
 def test_mixed_package_rejected_before_install(self):
  p=self.archive([('base.apk',apk()),('split.apk',apk('config.en',package='com.other.app'))])
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
  self.backend.install_set.assert_not_called()
 def test_mixed_version(self):
  p=self.archive([('base.apk',apk()),('split.apk',apk('config.en',version='8'))])
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
 def test_missing_base(self):
  p=self.archive([('split.apk',apk('config.en'))])
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
 def test_incompatible_abi(self):
  p=self.archive([('base.apk',apk()),('split.apk',apk('config.x86'))])
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
 def test_density_and_languages(self):
  p=self.archive([('base.apk',apk()),('hdpi.apk',apk('config.hdpi')),('xxhdpi.apk',apk('config.xxhdpi')),('en.apk',apk('config.en')),('zh.apk',apk('config.zh'))])
  self.backend.shell.return_value.stdout='Physical density: 320\nOverride density: 480\n';m.install_archive(p,self.backend,self.out)
  event=next(c for c in self.out.event.call_args_list if c.args[0]=='拆分选择');self.assertEqual(event.kwargs['splits'],['base','config.en','config.xxhdpi','config.zh'])
 def test_duplicate_split(self):
  p=self.archive([('base.apk',apk()),('a.apk',apk('config.en')),('b.apk',apk('config.en'))])
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
 def test_unknown_configuration(self):
  p=self.archive([('base.apk',apk()),('split.apk',apk('config.sdk35'))])
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
 def test_path_traversal(self):
  p=self.archive([('../base.apk',apk())])
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
  self.backend.install_set.assert_not_called()
 def test_duplicate_zip_entry(self):
  with self.assertWarns(UserWarning):p=self.archive([('base.apk',apk()),('base.apk',apk())])
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
 def test_bundletool_multivariant_rejected(self):
  p=self.archive([('toc.pb',b'protobuf'),('splits/base-master.apk',apk())],name='app.apks')
  with self.assertRaisesRegex(m.Failure,'bundletool'):m.install_archive(p,self.backend,self.out)
 def test_bundletool_universal(self):
  p=self.archive([('toc.pb',b'protobuf'),('universal.apk',apk())],name='app.apks');m.install_archive(p,self.backend,self.out);self.backend.install_set.assert_called_once()
 def test_failure_cleans_temp_retains_archive(self):
  p=self.archive([('base.apk',apk())]);self.backend.install_set.side_effect=m.Failure('Android rejected signature',5)
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
  self.assertTrue(p.exists());self.assertFalse(self.backend.install_set.call_args.args[0][0].exists())
 def test_postinstall_mismatch(self):
  p=self.archive([('base.apk',apk())]);self.backend.version.return_value=6
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
 def test_adb_install_multiple(self):
  b=object.__new__(m.Backend);b.mode='adb';b.prefix=['adb','-s','device'];b.out=self.out
  paths=[self.root/'base.apk',self.root/'split.apk']
  with patch.object(m,'run',return_value=Mock(returncode=0,stdout='Success\n',stderr='')) as run:
   b.install_set(paths);self.assertEqual(run.call_args.args[0],['adb','-s','device','install-multiple','-r']+[str(p) for p in paths])
 def root_install(self,write_failure=False,commit_failure=False):
  b=object.__new__(m.Backend);b.mode='root';b.prefix=['su','-c'];b.out=self.out;paths=[self.root/'0.apk',self.root/'1.apk']
  for p in paths:p.write_bytes(b'apk')
  calls=[]
  def run(cmd,**kwargs):
   calls.append(cmd[-1]);return Mock(returncode=0,stdout='Success: created install session [42]' if 'install-create' in cmd[-1] else ('Failure' if commit_failure and 'install-commit' in cmd[-1] else 'Success'),stderr='')
  with patch.object(m,'run',side_effect=run),patch.object(m.subprocess,'run',return_value=Mock(returncode=0,stdout=b'Failure' if write_failure else b'Success: streamed 3 bytes',stderr=b'')) as stream:
   if write_failure or commit_failure:
    with self.assertRaises(m.Failure):b.install_set(paths)
    self.assertIn('install-abandon 42',calls[-1])
   else:b.install_set(paths);self.assertNotIn('abandon',' '.join(calls));self.assertEqual(stream.call_count,2)
 def test_root_session_commit(self):self.root_install()
 def test_root_write_failure_abandons(self):self.root_install(write_failure=True)
 def test_root_commit_failure_abandons(self):self.root_install(commit_failure=True)
 def test_archive_download_hash(self):
  path=self.archive([('base.apk',apk())]);data=path.read_bytes();args=m.parser('apkm').parse_args(['install','--download-only','--output-dir',str(self.root/'out'),'app'])
  p={'source_url':'https://example.invalid/','url':'app.xapk','name':'app','version_code':7,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'format':'xapk'}
  with patch.object(m.urllib.request,'build_opener') as opener:
   opener.return_value.open.return_value=io.BytesIO(data);target=m.download(p,args,self.out)
  self.assertEqual(target.suffix,'.xapk');self.assertEqual(target.read_bytes(),data)
 def test_actual_apkg_subprocess_with_fake_adb(self):
  p=self.archive([('base.apk',apk()),('split.apk',apk('config.arm64_v8a'))]);bin=self.root/'bin';bin.mkdir();log=self.root/'log'
  adb=bin/'adb';adb.write_text('''#!/usr/bin/env python3
import os,sys,shlex,zipfile,json
from pathlib import Path
a=sys.argv[1:]
if a==['devices']:print('List of devices attached\\nFAKE\\tdevice');sys.exit(0)
assert a[:2]==['-s','FAKE'];a=a[2:]
if a[0]=='install-multiple':
 assert a[1]=='-r' and len(a)==4
 for p in a[2:]:
  with zipfile.ZipFile(p) as z:assert 'AndroidManifest.xml' in z.namelist()
 Path(os.environ['MOCK_LOG']).write_text(json.dumps(a));print('Success')
elif a[0]=='shell':
 cmd=shlex.split(a[1])
 if cmd==['getprop','ro.build.version.sdk']:print('35')
 elif cmd==['getprop','ro.product.cpu.abilist']:print('arm64-v8a')
 elif cmd[:2]==['dumpsys','package']:print('versionCode=7')
 else:sys.exit(8)
else:sys.exit(9)
''');adb.chmod(0o755)
  env=dict(os.environ,PATH=str(bin)+os.pathsep+os.environ['PATH'],MOCK_LOG=str(log))
  result=subprocess.run([os.sys.executable,str(ROOT/'src/apkm.py'),'--as-apkg','--mode','adb','--json','install',str(p)],env=env,text=True,capture_output=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr);events=[json.loads(line) for line in result.stdout.splitlines()];self.assertTrue(any(e['stage']=='结果' for e in events));self.assertTrue(p.exists());self.assertTrue(all(not Path(n).exists() for n in json.loads(log.read_text())[2:]))

 def test_unsupported_sdk(self):
  p=self.archive([('base.apk',apk(binary=False))]);self.backend.device_info.return_value=(19,['arm64-v8a'])
  with self.assertRaises(m.Failure):m.install_archive(p,self.backend,self.out)
 def test_symlink_archive(self):
  path=self.root/'symlink.xapk'
  with zipfile.ZipFile(path,'w') as z:
   i=zipfile.ZipInfo('base.apk');i.create_system=3;i.external_attr=0o120777<<16;z.writestr(i,b'elsewhere')
  with self.assertRaises(m.Failure):m.install_archive(path,self.backend,self.out)
 def test_declared_extraction_limit(self):
  fake=Mock();entry=Mock(filename='base.apk',external_attr=0,flag_bits=0,file_size=3*1024**3);fake.infolist.return_value=[entry]
  with self.assertRaises(m.Failure):m.archive_entries(fake)
 def test_feature_dependency(self):
  base={'path':Path('base.apk'),'package':'com.example.app','version':7,'split':'','target':'','native':set(),'min_sdk':1,'dependencies':[]}
  feature=dict(base,split='feature',dependencies=['missing'])
  with self.assertRaises(m.Failure):m.select_splits([base,feature],self.backend)
