import importlib.util, unittest, io, contextlib, os
from pathlib import Path
from unittest.mock import patch, Mock
spec=importlib.util.spec_from_file_location('apkm',Path(__file__).resolve().parents[1]/'src/apkm.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Remove(unittest.TestCase):
 def test_frontend_offline_and_deduplicated(self):
  with patch.object(m,'catalog',side_effect=AssertionError('no index')),patch.object(m,'Backend',side_effect=AssertionError('frontend must delegate')),patch.object(m,'invoke_apkg') as call:
   self.assertEqual(m.main(['--yes','remove','com.example.app','com.example.app']),0)
   self.assertEqual(call.call_args.args[0],['com.example.app']);self.assertEqual(call.call_args.kwargs['operation'],'remove')
 def test_invalid_batch_no_mutation(self):
  with patch.object(m,'invoke_apkg') as call,contextlib.redirect_stderr(io.StringIO()):
   self.assertEqual(m.main(['--yes','remove','com.example.app','bad;id']),2);call.assert_not_called()
 def test_confirmation_before_backend(self):
  with patch.object(m,'Backend') as backend,patch.object(m.sys.stdin,'isatty',return_value=False),contextlib.redirect_stderr(io.StringIO()):
   self.assertEqual(m.main(['remove','com.example.app']),2);backend.assert_not_called()
 def test_absent_skip(self):
  b=object.__new__(m.Backend);b.out=Mock();b.mode='adb';b.prefix=['adb'];b.installed=Mock(return_value=[])
  with patch.object(m,'run') as run:b.remove('com.example.app');run.assert_not_called()
 def test_success_checked(self):
  b=object.__new__(m.Backend);b.out=Mock();b.mode='adb';b.prefix=['adb'];b.installed=Mock(side_effect=[['com.example.app'],[]])
  with patch.object(m,'run',return_value=Mock(returncode=0,stdout='Success\n',stderr='')):b.remove('com.example.app')
 def test_false_success_rejected(self):
  b=object.__new__(m.Backend);b.out=Mock();b.mode='root';b.prefix=['su','-c'];b.installed=Mock(return_value=['com.example.app'])
  with patch.object(m,'run',return_value=Mock(returncode=0,stdout='Success',stderr='')):
   with self.assertRaises(m.Failure):b.remove('com.example.app')
 def test_help_languages(self):
  with patch.dict(os.environ,{'LC_ALL':'C'}):self.assertIn('Uninstall Android',m.parser('apkm').format_help())
  with patch.dict(os.environ,{'LC_ALL':'zh_CN.UTF-8'}):self.assertIn('卸载安卓',m.parser('apkm').format_help())
