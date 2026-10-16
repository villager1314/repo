import re,unittest
from pathlib import Path
class ReleaseMetadata(unittest.TestCase):
 def test_version_consistency(self):
  root=Path(__file__).resolve().parents[1]
  version=re.search(r"VERSION = '([^']+)'",(root/'src/apkm.py').read_text())[1]
  self.assertIn("VER='"+version+"'",(root/'scripts/build.py').read_text())
  self.assertIn("VERSION='"+version+"-1'",(root/'scripts/build_termux.py').read_text())
  for n in ['README.md','README.zh-CN.md']:self.assertIn('version-'+version+'-blue',(root/n).read_text())
  for n in ['apkm','apkg']:self.assertIn(n+' '+version,(root/'docs'/f'{n}.1').read_text().splitlines()[0])
  self.assertIn('<strong>v'+version+'</strong>',(root/'site/index.html').read_text())
