"""Loopback-only synthetic administration preview. Never a production auth mode."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'infra'))
from community import CommunityService
from server import PublicFiles, make_server


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8097)
    args=parser.parse_args()
    if args.port not in (8097,):
        raise SystemExit('The synthetic preview uses only the fixed loopback port 8097')
    owner={'sub':'synthetic-demo-owner','name':'Тестовый администратор','emailVerified':True}
    alice={'sub':'synthetic-demo-a','name':'Тестовый исследователь А','emailVerified':True}
    bob={'sub':'synthetic-demo-b','name':'Тестовый исследователь Б','emailVerified':True}
    with tempfile.TemporaryDirectory(prefix='ipvx-admin-demo-') as state:
        service=CommunityService(state,bootstrap_admin_sub=owner['sub'])
        people={}
        for user in [owner,alice,bob]:
            people[user['sub']]=service.handle('GET','/community/v1/session',user).data['author']['id']
        service.handle('POST','/community/v1/roles',owner,
                       {'authorId':people[alice['sub']],'role':'moderator','action':'grant','reason':'Синтетическое назначение модератора'},request_id='demo-role-1')
        service.handle('POST','/community/v1/rfcs/rfc-0006/entries',bob,
                       {'kind':'proposal','title':'Пример предложения к RFC','text':'Синтетическая запись для проверки модерации. Это не реальный вклад исследователя.'},request_id='demo-entry-1')

        class Demo(PublicFiles):
            def do_GET(self,head=False):
                if urlsplit(self.path).path=='/admin.html':
                    data=(self.server.root/'admin.html').read_text().replace('<main id="main">','<main id="main"><p class="note">Локальный предпросмотр с тестовыми пользователями. Все действия изменяют только временные демонстрационные данные; аккаунты ipvx.org не затрагиваются.</p>').encode()
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers()
                    if not head:self.wfile.write(data)
                    return
                super().do_GET(head)

            def proxy_auth(self,method):
                path=self.path
                if urlsplit(path).path.startswith('/auth/'):
                    result={'authenticated':True,'user':{'sub':'synthetic-demo-owner','name':owner['name'],'emailVerified':True},'demo':True}
                    status=200 if method in ('GET','HEAD') else 405
                else:
                    body=None
                    if method=='POST':
                        length=int(self.headers.get('Content-Length','0'))
                        if self.headers.get('Origin')!=f'http://127.0.0.1:{args.port}' or not 0<length<=12000:
                            self.send_error(403);return
                        try:body=json.loads(self.rfile.read(length))
                        except (ValueError,UnicodeError):self.send_error(400);return
                    response=service.handle('GET' if method=='HEAD' else method,path,owner,body,request_id=self.headers.get('Idempotency-Key'))
                    status,result=(response.status,response.data) if response else (404,{'error':'not_found'})
                data=json.dumps(result,ensure_ascii=False).encode()
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers()
                if method!='HEAD':self.wfile.write(data)

        server=make_server(args.root,'127.0.0.1',args.port,'0'*40)
        server.RequestHandlerClass=Demo
        try:server.serve_forever()
        finally:server.server_close()


if __name__=='__main__':main()
