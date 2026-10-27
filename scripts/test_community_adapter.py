"""Real localhost HTTP boundary with synthetic signed OIDC; no production user."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

from test_auth import FakeProvider, auth
from test_auth_proxy import module as public
from test_community import c


class CommunityAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        tree = self.root/'public';tree.mkdir();(tree/'index.html').write_text('Public research')
        self.provider = FakeProvider()
        self.community = c.CommunityService(self.root/'community', clock=lambda: self.provider.clock())
        self.service = auth.AuthService('client-1', 'pool-1', self.root/'auth', provider=self.provider,
                                        clock=lambda: self.provider.clock(), community=self.community)
        self.side = auth.make_auth_server(self.service, 0)
        self.front = public.make_server(tree, '127.0.0.1', 0, 'a'*40, self.side.server_port)
        self.threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (self.side, self.front)]
        for thread in self.threads:thread.start()
        self.counter = 0
        self.owner = self.sign_in('synthetic-confirmed-owner')
        # The operator confirms the signed-in account's own project pseudonym.
        owner_id = self.call('GET','/community/v1/session',self.owner)[2]['author']['id']
        self.community = c.CommunityService(self.root/'community', bootstrap_admin_author_id=owner_id,
                                           clock=lambda: self.provider.clock())
        self.service.community = self.community
        self.alice = self.sign_in('synthetic-participant-alice')
        self.bob = self.sign_in('synthetic-participant-bob')

    def tearDown(self):
        for server,thread in zip((self.front,self.side), reversed(self.threads)):
            server.shutdown();thread.join();server.server_close()
        self.tmp.cleanup()

    def raw(self, method, path, cookie=None, body=None, headers=None):
        merged = {'Host':'ipvx.org', **(headers or {})}
        if cookie:merged['Cookie']=cookie
        conn = http.client.HTTPConnection('127.0.0.1',self.front.server_port,timeout=4)
        conn.request(method,path,body=body,headers=merged)
        response=conn.getresponse();status=response.status;result_headers=response.getheaders();data=response.read();conn.close()
        return status,result_headers,data

    def call(self, method, path, cookie=None, value=None, *, key=None, headers=None):
        self.counter+=1
        extra={}
        body=None
        if method=='POST':
            body=json.dumps(value if value is not None else {},ensure_ascii=False).encode()
            extra={'Content-Type':'application/json','Origin':'https://ipvx.org',
                   'Sec-Fetch-Site':'same-origin','Idempotency-Key':key or 'adapter-%08d'%self.counter}
        status,hs,data=self.raw(method,path,cookie,body,{**extra,**(headers or {})})
        return status,dict(hs),json.loads(data)

    def sign_in(self, subject):
        self.provider.overrides={'sub':subject}
        status,hs,_=self.raw('GET','/auth/login')
        self.assertEqual(status,302)
        params=parse_qs(urlsplit(dict(hs)['Location']).query)
        tx=next(v.split(';')[0] for k,v in hs if k.lower()=='set-cookie')
        status,hs,_=self.raw('GET','/auth/callback?'+urlencode({'code':'synthetic','state':params['state'][0]}),tx)
        self.assertEqual(status,303)
        return next(v.split(';')[0] for k,v in hs if k.lower()=='set-cookie' and v.startswith(auth.SESSION_COOKIE+'='))

    def submit(self, cookie=None, *, text='Plain discussion', kind='proposal', key=None):
        status,_,data=self.call('POST','/community/v1/rfcs/rfc-0005/entries',cookie or self.alice,
                               {'kind':kind,'title':'Proposed revision','text':text},key=key)
        self.assertEqual(status,201,data)
        return data['entry']['id']

    def moderate(self, entry, action='publish'):
        status,_,data=self.call('POST','/community/v1/entries/%s/moderation'%entry,self.owner,
                               {'action':action,'reason':'Synthetic local review'})
        self.assertEqual(status,200,data)

    def test_signed_identity_pending_publication_hide_and_nonbinding_vote(self):
        entry=self.submit(text='<img src=x onerror=alert(1)> plain text',key='durable-http-1')
        own=self.call('GET','/community/v1/entries/%s'%entry,self.alice)
        self.assertEqual(own[0],200)
        self.assertIn('no-store',own[1]['Cache-Control']);self.assertEqual(own[1]['Vary'],'Cookie')
        self.assertEqual(own[1]['Referrer-Policy'],'no-referrer')
        self.assertEqual(self.call('GET','/community/v1/entries/%s'%entry,self.bob)[0],404)
        self.assertEqual(self.call('GET','/community/v1/rfcs/rfc-0005/entries?kind=proposal')[2]['entries'],[])
        self.assertEqual(self.call('GET','/community/v1/moderation',self.alice)[0],403)
        self.assertEqual(len(self.call('GET','/community/v1/moderation',self.owner)[2]['entries']),1)
        self.moderate(entry)
        published=self.call('GET','/community/v1/entries/%s'%entry)[2]['entry']
        self.assertEqual(published['text'],'<img src=x onerror=alert(1)> plain text')
        for identity in ('synthetic-participant-alice','fixture@example.invalid','access_token'):
            self.assertNotIn(identity,json.dumps(published))
        status,_,vote=self.call('POST','/community/v1/entries/%s/vote'%entry,self.bob,{'value':'yes'},key='vote-http-1')
        self.assertEqual(status,200);self.assertFalse(vote['binding'])
        self.assertEqual(vote['entry']['votes']['counts']['yes'],1)
        self.moderate(entry,'hide')
        self.assertEqual(self.call('GET','/community/v1/entries/%s'%entry)[0],404)
        self.assertEqual(self.call('POST','/community/v1/entries/%s/vote'%entry,self.bob,{'value':'yes'},key='vote-http-1')[0],404)
        self.assertEqual(self.call('GET','/community/v1/audit',self.bob)[0],403)
        self.assertIn('hide',[x['action'] for x in self.call('GET','/community/v1/audit',self.owner)[2]['events']])

    def test_identity_roles_and_origin_cannot_come_from_browser_input(self):
        path='/community/v1/rfcs/rfc-0005/entries'
        status,_,_=self.call('POST',path,None,{'text':'Anonymous'},headers={'X-User-Sub':'owner','X-User-Roles':'admin'})
        self.assertEqual(status,401)
        self.assertEqual(self.call('POST',path,self.alice,{'text':'Forged','user':{'sub':'owner','emailVerified':True}})[0],400)
        self.assertEqual(self.call('POST',path,self.alice,{'text':'Forged','role':'admin'})[0],400)
        self.assertEqual(self.call('GET','/community/v1/session',self.alice)[2]['roles'],['participant'])
        for extra in ({'Origin':'https://evil.invalid'},{'Origin':''},{'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.call('POST',path,self.alice,{'text':'CSRF'},headers=extra)[0],403)
        self.assertEqual(self.call('POST',path,self.alice,{'text':'Type'},headers={'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.call('GET','/community/v1/session',self.alice,headers={'Host':'www.ipvx.org'})[0],400)

    def test_json_idempotency_and_private_route_bounds(self):
        entry=self.submit(key='retry-http-1')
        self.assertEqual(self.submit(key='retry-http-1'),entry)
        self.assertEqual(len(self.call('GET','/community/v1/rfcs/rfc-0005/entries?kind=proposal&mine=1',self.alice)[2]['entries']),1)
        self.assertEqual(self.call('POST','/community/v1/rfcs/rfc-0005/entries',self.alice,{'text':'Different'},key='retry-http-1')[0],409)
        extra={'Origin':'https://ipvx.org','Content-Type':'application/json','Idempotency-Key':'malformed-http-1'}
        for raw in (b'{"text":"x","text":"y"}',b'{"text":NaN}',b'[]',b'\xff'):
            self.assertEqual(self.raw('POST','/community/v1/rfcs/rfc-0005/entries',self.alice,raw,extra)[0],400)
        for path in ('/community/v1/unknown','/community/v1/rfcs/rfc-9999/entries','/%63ommunity/v1/session',
                     '/api/mesh','/api/direct','/.env','/community.sqlite3','/author.key'):
            self.assertEqual(self.raw('GET',path,self.alice)[0],404,path)
        self.assertEqual(self.raw('GET','/community/v1/session',self.alice,headers={'Host':'evil.invalid'})[0],400)

    def test_expired_and_revoked_sessions_cannot_write(self):
        self.provider.rejected=True
        self.provider.clock=lambda:2_000_000_601
        self.assertEqual(self.call('POST','/community/v1/rfcs/rfc-0005/entries',self.alice,{'text':'Stale session'})[0],401)
        self.provider.rejected=False
        self.provider.clock=lambda:2_000_003_601
        self.assertEqual(self.call('POST','/community/v1/rfcs/rfc-0005/entries',self.bob,{'text':'Expired session'})[0],401)

    def test_admin_member_routes_and_immediate_suspension_through_both_proxies(self):
        alice = self.call('GET','/community/v1/session',self.alice)[2]['author']['id']
        self.assertEqual(self.call('GET','/community/v1/members',self.alice)[0],403)
        status,headers,body = self.call('GET','/community/v1/members',self.owner)
        self.assertEqual(status,200)
        self.assertIn(alice,[member['id'] for member in body['members']])
        self.assertIn('no-store',headers['Cache-Control'])
        path = '/community/v1/members/'+alice+'/access'
        self.assertEqual(self.call('POST',path,self.owner,{'action':'block','reason':'Owner suspension'})[0],200)
        self.assertEqual(self.call('POST','/community/v1/rfcs/rfc-0005/entries',self.alice,{'text':'Blocked message'})[0],403)
        self.assertEqual(self.call('GET','/community/v1/session',self.alice)[2]['access'],'blocked')
        self.assertEqual(self.call('POST',path,self.owner,{'action':'restore','reason':'Resume participation'})[0],200)
        self.assertEqual(self.call('POST','/community/v1/rfcs/rfc-0005/entries',self.alice,{'text':'Resumed message'})[0],201)

    def test_long_utf8_public_pages_fit_real_proxy(self):
        wanted=set()
        for _ in range(15):
            entry=self.submit(text='я'*5000);wanted.add(entry);self.moderate(entry)
        seen=set();before=None
        while True:
            path='/community/v1/rfcs/rfc-0005/entries?kind=proposal&limit=50'+('&before='+str(before) if before else '')
            status,_,data=self.call('GET',path)
            self.assertEqual(status,200,data)
            self.assertLess(len(json.dumps(data,ensure_ascii=False).encode()),131072)
            seen.update(x['id'] for x in data['entries'])
            before=data['nextBefore']
            if before is None:break
        self.assertEqual(seen,wanted)


if __name__=='__main__':
    unittest.main()
