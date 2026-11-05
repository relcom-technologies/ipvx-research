"""Bounded, certificate-pinned HTTPS. Only read RPC and Beacon API paths."""
import hashlib
import http.client
import json
import re
import ssl
import time
from urllib.parse import urlsplit

from bcp.wire import Reject, require

RPC_METHODS=frozenset(('eth_chainId','eth_syncing','web3_clientVersion','eth_getBlockByNumber',
                       'eth_getBlockByHash','eth_getCode','eth_call'))
BEACON_PATH=re.compile(r'/eth/(?:v1/(?:node/(?:syncing|version)|beacon/(?:genesis|headers/(?:finalized|0x[0-9a-f]{64})))|v2/beacon/blocks/0x[0-9a-f]{64})')
MAX_BODY=8*1024*1024


def strict_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    def bad(_):raise ValueError('non-finite JSON value')
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
    except (ValueError,UnicodeError,RecursionError):raise Reject('STATE_UNAVAILABLE') from None


class PinnedHTTPS:
    def __init__(self, endpoint, *, ssl_context=None):
        self.endpoint=endpoint
        self.context=ssl_context or ssl.create_default_context()
        if self.context.verify_mode!=ssl.CERT_REQUIRED or not self.context.check_hostname:
            raise ValueError('CA/hostname verification cannot be disabled')
        self._id=0

    def _exchange(self, method, path, body, timeout):
        deadline=time.monotonic()+timeout
        endpoint=urlsplit(self.endpoint.url)
        connection=http.client.HTTPSConnection(endpoint.hostname,endpoint.port or 443,timeout=timeout,context=self.context)
        try:
            connection.connect()
            cert=connection.sock.getpeercert(binary_form=True)
            require(cert and hashlib.sha256(cert).digest()==self.endpoint.certificate_sha256,'STATE_UNAVAILABLE')
            connection.request(method,(endpoint.path.rstrip('/') or '')+path,body=body,
                               headers={'Accept':'application/json','Content-Type':'application/json'})
            response=connection.getresponse()
            require(response.status==200,'STATE_UNAVAILABLE')  # no redirects/auth fallbacks
            require(response.getheader('Content-Encoding','identity').lower()=='identity','STATE_UNAVAILABLE')
            content_type=response.getheader('Content-Type','').split(';',1)[0].lower()
            require(content_type in ('application/json','application/problem+json'),'STATE_UNAVAILABLE')
            length=response.getheader('Content-Length')
            require(length is None or (length.isdecimal() and int(length)<=MAX_BODY),'STATE_UNAVAILABLE')
            chunks=[];size=0
            while True:
                remaining=deadline-time.monotonic()
                require(remaining>0,'STATE_UNAVAILABLE')
                # read1 avoids hiding a slow stream inside one unbounded read.
                # The response may own the socket after Connection: close.
                sock=connection.sock or response.fp.raw._sock
                sock.settimeout(remaining)
                chunk=response.read1(min(65536,MAX_BODY+1-size))
                if not chunk:break
                chunks.append(chunk);size+=len(chunk)
                require(size<=MAX_BODY,'STATE_UNAVAILABLE')
                if response.isclosed():break
            raw=b''.join(chunks)
            require(len(raw)<=MAX_BODY,'STATE_UNAVAILABLE')
            return strict_json(raw)
        except (OSError,http.client.HTTPException,ValueError,RecursionError,AttributeError):
            raise Reject('STATE_UNAVAILABLE') from None
        finally:connection.close()

    def beacon(self, path, timeout):
        require(BEACON_PATH.fullmatch(path) is not None,'STATE_UNAVAILABLE')
        result=self._exchange('GET',path,None,timeout)
        require(type(result) is dict,'STATE_UNAVAILABLE')
        return result

    def batch(self, calls, timeout):
        require(0<len(calls)<=256 and all(method in RPC_METHODS for method,_ in calls),'STATE_UNAVAILABLE')
        items=[]
        for method,params in calls:
            self._id+=1
            items.append({'jsonrpc':'2.0','id':self._id,'method':method,'params':params})
        result=self._exchange('POST','/',json.dumps(items,separators=(',',':')).encode(),timeout)
        require(type(result) is list and len(result)==len(items),'STATE_UNAVAILABLE')
        by_id={}
        for value in result:
            require(type(value) is dict and value.get('jsonrpc')=='2.0' and type(value.get('id')) is int,'STATE_UNAVAILABLE')
            require(value['id'] not in by_id and 'result' in value and 'error' not in value,'STATE_UNAVAILABLE')
            by_id[value['id']]=value['result']
        require(set(by_id)=={item['id'] for item in items},'STATE_UNAVAILABLE')
        return [by_id[item['id']] for item in items]
