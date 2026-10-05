#!/usr/bin/env python3
"""Add a single APK to the repository using aapt metadata; re-sign its index."""
import argparse, hashlib, json, re, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from apkm import check_apk,validate_index
p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('apk',type=Path);p.add_argument('--key',required=True);p.add_argument('--description',default='');a=p.parse_args()
if not re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9._+-]*',a.name):p.error('invalid software name')
check_apk(a.apk)
data=subprocess.run(['aapt','dump','badging',str(a.apk)],check=True,capture_output=True,text=True).stdout
package=re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'",data,re.M)
sdk=re.search(r"^sdkVersion:'(\d+)'",data,re.M)
if not package:raise SystemExit('Cannot read APK package metadata')
if re.search(r"^package:.*\bsplit='",data,re.M) or re.search(r'^uses-split:',data,re.M):raise SystemExit('Split APK is not supported')
native=re.search(r'^native-code: (.*)$',data,re.M)
abis=re.findall(r"'([^']+)'",native[1]) if native else ['any']
b=a.apk.read_bytes();sha=hashlib.sha256(b).hexdigest();filename=f'{a.name}-{package[2]}-{sha[:12]}.apk'
entry={'name':a.name,'package_id':package[1],'version_code':int(package[2]),'version_name':package[3],'min_sdk':int(sdk[1]) if sdk else 1,'abis':abis,'url':'apks/'+filename,'size':len(b),'sha256':sha,'description':a.description}
index=ROOT/'site/android/index.json';content=json.loads(index.read_text())
content['packages']=[e for e in content['packages'] if e['name']!=a.name]+[entry];content['revision']+=1
validate_index(content)
shutil.copy(a.apk,ROOT/'site/android/apks'/filename)
index.write_text(json.dumps(content,indent=2,ensure_ascii=False)+'\n')
subprocess.run(['gpg','--batch','--yes','--local-user',a.key,'--detach-sign','--output',str(index)+'.sig',str(index)],check=True)
print('Added',a.name,package[1],package[2])
