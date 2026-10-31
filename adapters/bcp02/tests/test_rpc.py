from hashlib import sha256
import json
import socket
import ssl
import unittest
from unittest.mock import MagicMock,patch

from bcp.wire import Reject
from adapters.bcp02.binding import Endpoint
from adapters.bcp02.rpc import PinnedHTTPS,strict_json,MAX_BODY


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(socket.socket,'connect',side_effect=AssertionError('live network forbidden')).start()
        self.cert=b'offline certificate DER fixture'
        self.endpoint=Endpoint('https://el.invalid/rpc',sha256(self.cert).digest())
        self.transport=PinnedHTTPS(self.endpoint)

    def exchange(self,raw=b'{}',*,status=200,headers=None,cert=None):
        self.connection=MagicMock();self.connection.sock.getpeercert.return_value=self.cert if cert is None else cert
        response=self.connection.getresponse.return_value;response.status=status
        response.isclosed.return_value=False
        values={'Content-Type':'application/json',**(headers or {})}
        response.getheader.side_effect=lambda name,default=None:values.get(name,default)
        response.read1.side_effect=[raw,b'']
        self.factory=patch('adapters.bcp02.rpc.http.client.HTTPSConnection',return_value=self.connection).start()
        return self.transport._exchange('GET','/eth/v1/beacon/genesis',None,1)

    def test_authenticated_pin_before_http_request_and_no_redirect(self):
        self.assertEqual(self.exchange(),{})
        self.assertEqual(self.connection.method_calls[0][0],'connect')
        self.connection.request.assert_called_once()
        self.assertEqual(self.connection.request.call_args.args[1],'/rpc/eth/v1/beacon/genesis')
        self.connection.close.assert_called_once()
        with self.assertRaises(Reject):self.exchange(cert=b'other-certificate')
        self.connection.request.assert_not_called()
        with self.assertRaises(Reject):self.exchange(status=302)
        self.connection.request.assert_called_once()  # redirect not followed

    def test_tls_cannot_be_disabled_and_network_errors_are_sanitized(self):
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False
        with self.assertRaises(ValueError):PinnedHTTPS(self.endpoint,ssl_context=context)
        with patch('adapters.bcp02.rpc.http.client.HTTPSConnection') as factory:
            factory.return_value.connect.side_effect=OSError('private diagnostic must not leak')
            with self.assertRaises(Reject) as caught:self.transport._exchange('POST','/',b'[]',1)
            self.assertEqual(str(caught.exception),'STATE_UNAVAILABLE')

    def test_http_encoding_type_size_and_malformed_json_failures(self):
        for raw,headers in [(b'{}',{'Content-Encoding':'gzip'}),(b'{}',{'Content-Type':'text/html'}),
            (b'{}',{'Content-Length':str(MAX_BODY+1)}),(b'{}',{'Content-Length':'-1'}),
            (b'x'*(MAX_BODY+1),{}),(b'{bad',{}),(b'{"x":1,"x":2}',{}),(b'{"x":NaN}',{})]:
            with self.subTest(headers=headers,size=len(raw)),self.assertRaises(Reject):self.exchange(raw,headers=headers)

    def test_slow_body_deadline_is_checked_between_chunks(self):
        with patch('adapters.bcp02.rpc.time.monotonic',side_effect=[0,2]):
            with self.assertRaises(Reject):self.exchange()

    def test_content_length_completion_closes_response_socket(self):
        # HTTPResponse closes its fp immediately after its last declared byte.
        connection=MagicMock();connection.sock=None
        response=connection.getresponse.return_value;response.status=200
        response.fp.raw._sock.getpeercert.return_value=self.cert
        connection.connect.side_effect=lambda:setattr(connection,'sock',response.fp.raw._sock)
        connection.request.side_effect=lambda *a,**k:setattr(connection,'sock',None)
        response.getheader.side_effect=lambda k,d=None:{'Content-Type':'application/json'}.get(k,d)
        response.read1.return_value=b'{}';response.isclosed.return_value=True
        with patch('adapters.bcp02.rpc.http.client.HTTPSConnection',return_value=connection):
            self.assertEqual(self.transport._exchange('GET','/eth/v1/beacon/genesis',None,1),{})
        response.read1.assert_called_once()

    def test_batch_reorders_exact_ids_and_rejects_partial_error_duplicate(self):
        def response(method,path,body,timeout):
            requests=json.loads(body)
            return [{'jsonrpc':'2.0','id':r['id'],'result':r['method']} for r in reversed(requests)]
        calls=[('eth_chainId',[]),('eth_syncing',[])]
        with patch.object(self.transport,'_exchange',side_effect=response):
            self.assertEqual(self.transport.batch(calls,1),['eth_chainId','eth_syncing'])
        for kind in ('partial','error','duplicate','wrong-id','bool-id','wrong-version'):
            def bad(method,path,body,timeout):
                values=response(method,path,body,timeout)
                if kind=='partial':values.pop()
                if kind=='error':values[0]['error']={'code':-32000,'message':'private'}
                if kind=='duplicate':values[0]['id']=values[1]['id']
                if kind=='wrong-id':values[0]['id']=999999
                if kind=='bool-id':values[0]['id']=True
                if kind=='wrong-version':values[0]['jsonrpc']='1.0'
                return values
            with self.subTest(kind=kind),patch.object(self.transport,'_exchange',side_effect=bad),self.assertRaises(Reject):
                self.transport.batch(calls,1)

    def test_write_methods_and_nonallowlisted_beacon_paths_never_reach_io(self):
        with patch.object(self.transport,'_exchange') as io:
            for method in ('eth_sendRawTransaction','eth_sendTransaction','personal_unlockAccount','debug_traceCall'):
                with self.subTest(method=method),self.assertRaises(Reject):self.transport.batch([(method,[])],1)
            for path in ('/eth/v1/beacon/headers/head','/eth/v1/beacon/headers/safe','/eth/v1/validator/prepare_beacon_proposer'):
                with self.subTest(path=path),self.assertRaises(Reject):self.transport.beacon(path,1)
            io.assert_not_called()

    def test_strict_json_has_no_duplicate_or_nonfinite_escape(self):
        self.assertEqual(strict_json(b'{"ok":[1,false,null]}'),{'ok':[1,False,None]})
        for value in (b'{"a":{},"a":0}',b'Infinity',b'-Infinity',b'NaN',b'\xff'):
            with self.subTest(value=value),self.assertRaises(Reject):strict_json(value)

if __name__=='__main__':unittest.main()
