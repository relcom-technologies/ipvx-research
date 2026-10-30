"""Only the two approved public GitHub threads; no login/token or private intake."""
from html.parser import HTMLParser
import json
import re
import ssl
import urllib.request

DISCUSSION='https://github.com/a2aproject/A2A/discussions/2406'
ISSUE='https://github.com/eliswedtlv/ClawMesh/issues/1'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('public_redirect_rejected')


def fetch(url,json_data=False):
    if not (url==DISCUSSION or re.fullmatch(
            r'https://api.github.com/repos/eliswedtlv/ClawMesh/issues/1/comments\?per_page=100&page=\d{1,2}',url)):
        raise ValueError('source_not_authorized')
    opener=urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req=urllib.request.Request(url,headers={'User-Agent':'IPvX-Public-Analysis/1.0','Cache-Control':'no-cache'})
    with opener.open(req,timeout=20) as response:raw=response.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ValueError('public_response_limit')
    return json.loads(raw) if json_data else raw.decode('utf-8')


class Node:
    def __init__(self,tag='',attrs=()):self.tag,self.attrs,self.children=tag,dict(attrs),[]
    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child,Node):yield from child.walk()
    def text(self):
        if self.tag in ('script','style','template','svg'):return ''
        return ' '.join(c.text() if isinstance(c,Node) else c for c in self.children)


class Page(HTMLParser):
    def __init__(self):super().__init__();self.root=Node();self.stack=[self.root]
    def handle_starttag(self,tag,attrs):
        node=Node(tag,attrs);self.stack[-1].children.append(node)
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):self.stack.append(node)
    def handle_startendtag(self,tag,attrs):self.stack[-1].children.append(Node(tag,attrs))
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):self.stack[-1].children.append(data)


def discussion(html=None,owner=None):
    page=Page();page.feed(fetch(DISCUSSION) if html is None else html)
    nodes=list(page.root.walk())
    headers=[n for n in nodes if n.attrs.get('id')=='discussion-comment-count']
    if len(headers)!=1 or not re.search(r'\b[0-9,]+\s+comments?\b',headers[0].text()):
        raise ValueError('github_visible_page_unavailable')
    count=int(re.search(r'([0-9,]+)\s+comments?\b',headers[0].text())[1].replace(',',''))
    rows=[];seen=set()
    for node in nodes:
        identifier=node.attrs.get('id','')
        if not re.fullmatch(r'discussioncomment-\d+',identifier) or identifier in seen:continue
        children=list(node.walk())
        bodies=[n for n in children if 'js-comment-body' in n.attrs.get('class','').split()]
        authors=[n for n in children if n.tag=='a' and n.attrs.get('data-hovercard-type')=='user'
            and re.fullmatch(r'/[A-Za-z0-9-]{1,39}',n.attrs.get('href',''))]
        if not bodies or not authors:continue
        text=bodies[0].text().strip()
        if not text or len(text)>16000:raise ValueError('github_body_limit')
        actor=authors[0].attrs['href'][1:]
        times=[n.attrs['datetime'] for n in children if n.tag=='relative-time' and 'datetime' in n.attrs]
        rows.append(dict(id='a2a-community:'+identifier,source='a2a-community',source_url=DISCUSSION+'#'+identifier,
            claimed_author=actor,project_account=actor.lower()==(owner or '').lower(),text=text,
            created_at=times[0] if times else None,updated_at=None,a2a_submission=False))
        seen.add(identifier)
    if count and not rows:raise ValueError('github_comment_bodies_unavailable')
    return rows,dict(checked=True,complete=False,mode='visible_public_html_only',reported_comments=count,
        returned_comments=len(rows),known_limit='Hidden/paginated replies are not proven complete; no authenticated GitHub API token is deployed.')


def claw(owner=None):
    result=[]
    for page in range(1,21):
        rows=fetch(f'https://api.github.com/repos/eliswedtlv/ClawMesh/issues/1/comments?per_page=100&page={page}',True)
        if not isinstance(rows,list):raise ValueError('github_issue_format')
        for row in rows:
            actor=(row.get('user') or {}).get('login','unknown')
            text=row['body']
            if not isinstance(text,str) or len(text)>16000:raise ValueError('github_body_limit')
            if not re.fullmatch(re.escape(ISSUE)+r'#issuecomment-\d+',row['html_url']):raise ValueError('github_permalink')
            result.append(dict(id='clawmesh:'+str(row['id']),source='clawmesh',source_url=row['html_url'],
                claimed_author=actor,project_account=actor.lower()==(owner or '').lower(),text=text,
                created_at=row['created_at'],updated_at=row['updated_at'],a2a_submission=False))
        if len(rows)<100:return result,dict(checked=True,complete=True,returned_comments=len(result))
    raise ValueError('github_issue_pagination_limit')


def collect(owner=None):
    rows=[];coverage={}
    for name,reader in [('a2a-community',lambda:discussion(owner=owner)),('clawmesh',lambda:claw(owner))]:
        try:
            found,status=reader();rows+=found;coverage[name]=status
        except Exception:coverage[name]=dict(checked=False,complete=False,code='public_source_unavailable')
    return rows,coverage
