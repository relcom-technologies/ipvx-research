import json,re
from pathlib import Path
from html.parser import HTMLParser
root=Path(__file__).resolve().parents[1]
errors=[]
class Check(HTMLParser):
 def __init__(self,path):super().__init__();self.path=path;self.h1=0
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if tag=='h1':self.h1+=1
  for key in ('href','src'):
   v=d.get(key,'')
   if v and not v.startswith(('http:','https:','mailto:','#','data:')) and not (root/v.split('#')[0].split('?')[0]).exists():errors.append(f'{self.path.name}: missing {v}')
for p in root.glob('*.html'):
 c=Check(p);c.feed(p.read_text())
 if c.h1!=1:errors.append(f'{p.name}: expected one h1, got {c.h1}')
for p in [*root.glob('*.html'),*root.glob('data/*.json'),*root.glob('assets/*.js')]:
 s=p.read_text()
 if re.search(r'10\.10\.50\.|BEGIN (?:OPENSSH|RSA) PRIVATE KEY|DIRECT_ADMIN_TOKEN|MESH_ADMIN_TOKEN|ghp_[A-Za-z0-9]{20}',s):errors.append(f'{p.name}: private management material')
for p in root.glob('data/*.json'):json.loads(p.read_text())
if errors:raise SystemExit('\n'.join(errors))
print('12 pages: links, h1, public-data boundaries, JSON checked')
