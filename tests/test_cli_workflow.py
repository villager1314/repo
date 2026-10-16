import contextlib,io,importlib.util,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('apkm',Path(__file__).resolve().parents[1]/'src/apkm.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Workflow(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.p=dict(name='demo',package_id='com.example.app',version_code=7,version_name='7',min_sdk=21,abis=['any'],sha256='a'*64,size=10,url='app.apk',source_url='https://example.org')
  self.backend=Mock(mode='adb',prefix=['adb','-s','FAKE']);self.backend.device_info.return_value=(35,['arm64-v8a']);self.backend.version.return_value=7
 def tearDown(self):self.tmp.cleanup()
 def main(self,args,program='apkm'):
  with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):return m.main(args,program=program)
 def test_aliases_and_global_position(self):
  self.assertEqual(m.normalize_cli(['--mode','adb','-i','file.apk','-y'],'apkg'),['--mode','adb','-y','install','file.apk'])
  self.assertEqual(m.normalize_cli(['install','--','-y'],'apkg'),['install','--','-y'])
  self.assertEqual(m.normalize_cli(['--serial','-i','-l'],'apkg'),['--serial','-i','list'])
 def test_show_and_download(self):
  with patch.object(m,'catalog',return_value={'demo':self.p}),patch.object(m,'Backend',side_effect=AssertionError('offline')),patch.object(m,'download',return_value=self.root/'app.apk') as download:
   self.assertEqual(self.main(['show','demo']),0);self.assertEqual(self.main(['download','demo']),0);download.assert_called_once()
 def test_local_frontend_skips_sources(self):
  path=self.root/'file.apk';path.write_bytes(b'fixture')
  with patch.object(m,'catalog',side_effect=AssertionError('no source')),patch.object(m,'invoke_apkg') as invoke:
   self.assertEqual(self.main(['install',str(path)]),0);invoke.assert_called_once()
 def test_reinstall_only_equal_not_downgrade(self):
  with patch.object(m,'catalog',return_value={'demo':self.p}),patch.object(m,'Backend',return_value=self.backend),patch.object(m,'download',return_value=self.root/'app.apk') as download,patch.object(m,'invoke_apkg'),patch.object(m,'cleanup_apk'):
   self.assertEqual(self.main(['install','demo']),0);download.assert_not_called()
   self.assertEqual(self.main(['reinstall','demo']),0);download.assert_called_once();download.reset_mock();self.backend.version.return_value=8
   self.assertEqual(self.main(['reinstall','demo']),0);download.assert_not_called()
 def test_repository_list_offline_and_upgradable(self):
  self.backend.installed.return_value=['com.example.app']
  with patch.object(m,'catalog',return_value={'demo':self.p}),patch.object(m,'Backend',side_effect=AssertionError('offline')):
   self.assertEqual(self.main(['list','de*']),0)
  with patch.object(m,'catalog',return_value={'demo':self.p}),patch.object(m,'Backend',return_value=self.backend),contextlib.redirect_stdout(io.StringIO()) as out:
   self.backend.version.return_value=6;self.assertEqual(m.main(['list','--upgradable']),0)
   self.assertIn('demo',out.getvalue())
 def test_local_information_without_device(self):
  path=self.root/'file.apk'
  with zipfile.ZipFile(path,'w') as z:z.writestr('AndroidManifest.xml','<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.app" android:versionCode="7"/>')
  with patch.object(m,'Backend',side_effect=AssertionError('offline')):
   self.assertEqual(self.main(['-I',str(path)],'apkg'),0);self.assertEqual(self.main(['-c',str(path)],'apkg'),0)
 def test_clean_preserves_unknown_files_indexes_and_symlinks(self):
  cache=self.root/'cache';folder=cache/'apks';folder.mkdir(parents=True);managed=folder/'demo-7-aaaaaaaaaaaa.apk';managed.write_bytes(b'cached');unknown=folder/'personal.apk';unknown.write_bytes(b'user');outside=self.root/'outside';outside.write_text('keep');(folder/'linked-7-bbbbbbbbbbbb.apk').symlink_to(outside)
  config=self.root/'config';m.write_json(config/'indexes/test.json',{'keep':True})
  with patch.object(m,'CACHE',cache),patch.object(m,'CONFIG',config):
   self.assertEqual(self.main(['clean','-y']),0)
  self.assertFalse(managed.exists());self.assertTrue(unknown.exists());self.assertTrue(outside.exists());self.assertTrue((config/'indexes/test.json').exists())
 def test_clean_requires_confirmation(self):
  folder=self.root/'cache/apks';folder.mkdir(parents=True);(folder/'demo-7-aaaaaaaaaaaa.apk').write_bytes(b'cache')
  with patch.object(m,'CACHE',self.root/'cache'),patch.object(m,'CONFIG',self.root/'config'),patch.object(m.sys.stdin,'isatty',return_value=False):self.assertEqual(self.main(['clean']),2)
 def test_simulation_install_and_remove_never_mutate(self):
  with patch.object(m,'catalog',return_value={'demo':self.p}),patch.object(m,'Backend',return_value=self.backend),patch.object(m,'download',side_effect=AssertionError('no network')),patch.object(m,'invoke_apkg',side_effect=AssertionError('no mutation')):
   self.backend.version.return_value=None
   self.assertEqual(self.main(['install','demo','-s']),0);self.assertEqual(self.main(['remove','com.example.app','--simulate']),0)
 def test_simulation_rejects_mutating_other_commands(self):
  with patch.object(m,'refresh',side_effect=AssertionError('no update')):self.assertEqual(self.main(['--simulate','update']),2)
 def test_simulated_clean_preserves_files(self):
  folder=self.root/'cache/apks';folder.mkdir(parents=True);p=folder/'demo-7-aaaaaaaaaaaa.apk';p.write_bytes(b'x')
  with patch.object(m,'CACHE',self.root/'cache'),patch.object(m,'CONFIG',self.root/'config'):self.assertEqual(self.main(['clean','-s']),0)
  self.assertTrue(p.exists())
 def test_source_selection_and_pinned_versions(self):
  config=self.root/'config';sources={}
  for source in ['a','b']:
   sources[source]={'url':'https://'+source+'.example','keyring':'key'};package=dict(self.p);package.pop('source_url');m.write_json(config/f'indexes/{source}.json',{'schema_version':1,'revision':1,'packages':[package]})
  m.write_json(config/'sources.json',sources)
  with patch.object(m,'CONFIG',config),contextlib.redirect_stdout(io.StringIO()):
   with self.assertRaises(m.Failure):m.catalog(Mock())
   selected=m.catalog(Mock(),'b');self.assertEqual(selected['demo']['source_name'],'b')
   self.assertEqual(self.main(['show','demo','--source','a']),0)
  older=dict(self.p,version_code=6);package=dict(self.p,variants=[self.p,older]);self.assertEqual(m.resolve_package({'demo':package},'demo=6')['version_code'],6)
  with self.assertRaises(m.Failure):m.resolve_package({'demo':package},'demo=4')
 def test_hold_is_target_scoped_and_upgrade_respects_it(self):
  with patch.object(m,'CONFIG',self.root/'config'),patch.object(m,'Backend',return_value=self.backend),patch.object(m,'catalog',return_value={'demo':self.p}),patch.object(m,'download',side_effect=AssertionError('held')):
   self.assertEqual(self.main(['hold','com.example.app']),0);self.backend.installed.return_value=['com.example.app'];self.backend.version.return_value=6
   self.assertEqual(self.main(['upgrade']),0);self.assertIn('com.example.app',m.target_holds(self.backend));self.backend.prefix=['adb','-s','OTHER'];self.assertEqual(m.target_holds(self.backend),[])
 def test_remove_friendly_name_resolves(self):
  with patch.object(m,'catalog',return_value={'demo':self.p}),patch.object(m,'invoke_apkg') as invoke:
   self.assertEqual(self.main(['remove','demo','-y']),0);self.assertEqual(invoke.call_args.args[0],['com.example.app'])
 def test_bundletool_optional_dependency_and_device_spec(self):
  jar=self.root/'bundletool.jar';jar.write_bytes(b'fixture');archive=self.root/'app.apks';archive.write_bytes(b'zip')
  self.backend.shell.side_effect=lambda args:Mock(stdout='Physical density: 480\n' if args==['wm','density'] else 'zh-CN,en-US')
  def extract(cmd,**kw):
   self.assertIn('extract-apks',cmd);specpath=next(x.split('=',1)[1] for x in cmd if x.startswith('--device-spec='))
   import json
   data=json.loads(Path(specpath).read_text());self.assertEqual(data['screenDensity'],480);self.assertEqual(data['supportedAbis'],['arm64-v8a']);self.assertEqual(data['supportedLocales'],['zh-CN','en-US'])
   output=Path(next(x.split('=',1)[1] for x in cmd if x.startswith('--output-dir=')));output.mkdir();(output/'base.apk').write_bytes(b'fixture');return Mock(returncode=0,stdout='',stderr='')
  temp=self.root/'extract';temp.mkdir()
  with patch.object(m.shutil,'which',return_value='/usr/bin/java'),patch.object(m,'run',side_effect=extract):self.assertEqual(len(m.extract_with_bundletool(archive,self.backend,temp,jar)),1)
  with patch.object(m.shutil,'which',return_value=None):
   with self.assertRaises(m.Failure):m.extract_with_bundletool(archive,self.backend,temp,jar)
 def test_bundletool_failure_cannot_install(self):
  jar=self.root/'tool.jar';jar.write_bytes(b'fixture');path=self.root/'app.apks'
  with zipfile.ZipFile(path,'w') as z:z.writestr('toc.pb',b'fixture');z.writestr('base-master.apk',b'fixture')
  with patch.object(m,'extract_with_bundletool',side_effect=m.Failure('failed extraction',4)):
   with self.assertRaises(m.Failure):m.install_archive(path,self.backend,Mock(),str(jar))
  self.backend.install_set.assert_not_called()
 def test_global_flags_after_command_and_short_download(self):
  with patch.object(m,'catalog',return_value={'demo':self.p}),patch.object(m,'Backend',side_effect=AssertionError('download is offline from device')),patch.object(m,'download',return_value=self.root/'app.apk') as download:
   self.assertEqual(self.main(['-d','install','demo']),0);download.assert_called_once()
 def test_unambiguous_parameters_and_offline_local_simulation(self):
  with contextlib.redirect_stderr(io.StringIO()):
   with self.assertRaises(SystemExit):m.parser('apkm').parse_args(['--ser','FAKE','doctor'])
  path=self.root/'file.apk'
  with zipfile.ZipFile(path,'w') as z:z.writestr('AndroidManifest.xml','<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.app" android:versionCode="7"/>')
  with patch.object(m,'Backend',side_effect=AssertionError('offline dry run')):self.assertEqual(self.main(['install',str(path),'--simulate'],'apkg'),0)
 def test_dpkg_style_actions_end_to_end(self):
  path=self.root/'app.apk'
  with zipfile.ZipFile(path,'w') as z:z.writestr('AndroidManifest.xml',b'fixture')
  self.backend.shell.return_value.stdout='package:/data/app/base.apk\n';self.backend.installed.return_value=['com.example.app']
  with patch.object(m,'Backend',return_value=self.backend):
   self.assertEqual(self.main(['-i',str(path)],'apkg'),0);self.backend.install.assert_called_once()
   self.assertEqual(self.main(['-r','com.example.app','-y'],'apkg'),0);self.backend.remove.assert_called_once_with('com.example.app')
   self.assertEqual(self.main(['-s','com.example.app'],'apkg'),0);self.assertEqual(self.main(['-l','com.example.*'],'apkg'),0)
