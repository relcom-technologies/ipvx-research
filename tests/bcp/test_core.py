import random
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from bcp import build
from bcp.core import Core, HPKE
from bcp.journal import Journal
from bcp.wire import Reject, decode, digest, ethernet, hpke_info, uint
from fixtures import (PROFILE, FIXTURE, SPEC, BY_ID, NOW, MONO, state, snapshot,
                      core_for, receive, signing, encryption)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.core = core_for(BY_ID['V07-DATA-R-B'])
        self.addCleanup(self.core.journal.close)

    def assert_reject(self, code, function, *args, **kwargs):
        with self.assertRaises(Reject) as e:
            function(*args,**kwargs)
        self.assertEqual(e.exception.code,code)

    def test_frozen_bad_session_and_corrected_request_hash(self):
        v = BY_ID['N29-REQUEST-HASH']
        self.assert_reject('AUTH_FAILED',receive,self.core,v)
        original = decode(bytes.fromhex(v['bcp_hex']),PROFILE)
        corrected = build.rewrap(original,bytes.fromhex(FIXTURE['sessions'][1]['session_id_hex']),1,1,signing(3))
        self.assertEqual(corrected.fields['immutable'],original.fields['immutable'])
        f=corrected.fields
        plain=HPKE.decrypt(f['enc']+f['ciphertext'],encryption(2),info=hpke_info(corrected))
        self.assertNotEqual(digest(plain),f['request_hash'])
        self.assert_reject('INVALID_PAYLOAD',self.core.receive,
            ethernet(self.core.local_mac,bytes.fromhex('020000000003'),corrected.encode()),now=NOW,monotonic=MONO,clock_trusted=True)

    def test_generated_encryption_delivery_and_rewrap(self):
        view = self.core.state;nodes=view.packet.nodes;policy=next(p for p in view.packet.connections.values() if p.source == 1)
        edges=tuple((e.rule,e.version) for a,b in ((1,3),(3,2)) for e in view.packet.edges.values() if (e.source,e.destination)==(a,b))
        first = build.packet(PROFILE,5,view.packet.checkpoint,nodes[1],nodes[2],policy,b'm'*32,b'p'*32,b'new binary request',
            (1,3,2),edges,bytes.fromhex(FIXTURE['sessions'][0]['session_id_hex']),1,0,signing(1),signing(1),encryption(2).public_key(),
            issued=NOW,expires=NOW+60)
        relay = core_for(BY_ID['V06-DATA-A-R']);self.addCleanup(relay.journal.close)
        d = relay.receive(ethernet(relay.local_mac,bytes.fromhex('020000000001'),first.encode()),now=NOW,monotonic=MONO,clock_trusted=True)
        self.assertEqual(d.action,'FORWARD');self.assertIsNone(d.plaintext)
        second = build.rewrap(first,bytes.fromhex(FIXTURE['sessions'][1]['session_id_hex']),1,1,signing(3))
        self.assertEqual(first.fields['immutable'],second.fields['immutable'])
        d = self.core.receive(ethernet(self.core.local_mac,bytes.fromhex('020000000003'),second.encode()),now=NOW,monotonic=MONO,clock_trusted=True)
        self.assertEqual((d.action,d.disposition,d.plaintext),('DELIVER','NEW',b'new binary request'))
        again = build.rewrap(first,second.fields['session'],2,1,signing(3))
        d = self.core.receive(ethernet(self.core.local_mac,bytes.fromhex('020000000003'),again.encode()),now=NOW,monotonic=MONO,clock_trusted=True)
        self.assertEqual(d.disposition,'DUPLICATE')

    def test_control_builders_reproduce_frozen_bytes(self):
        v=decode(bytes.fromhex(BY_ID['V01-HELLO']['bcp_hex']),PROFILE);f=v.fields
        self.assertEqual(build.hello(PROFILE,f['node'],f['epoch'],f['nonce'],f['checkpoint'],f['roles'],f['mac'],signing(f['node'])).encode(),v.encode())
        for name,kind,nft in (('V02-CHALLENGE',2,3),('V03-CONFIRM',3,1)):
            v=decode(bytes.fromhex(BY_ID[name]['bcp_hex']),PROFILE)
            self.assertEqual(build.handshake(PROFILE,kind,v.body[:248],signing(nft)).encode(),v.encode())
        for name in ('V04-ROUTE-ORIGIN','V05-ROUTE-SUFFIX'):
            v=decode(bytes.fromhex(BY_ID[name]['bcp_hex']),PROFILE);f=v.fields
            made=build.route(PROFILE,f['session'],f['sequence'],f['checkpoint'],f['nonce'],f['issued'],f['expires'],f['nodes'],f['edges'],
                             [signing(n) for n in f['path']],signing(f['path'][0]))
            self.assertEqual(made.encode(),v.encode())

    def test_no_replay_poisoning_by_bad_signature_or_binding(self):
        v=BY_ID['V07-DATA-R-B'];good=bytes.fromhex(v['ethernet_hex'])
        bad=bytearray(good);bad[-1]^=1
        self.assert_reject('AUTH_FAILED',self.core.receive,bytes(bad),now=NOW,monotonic=MONO,clock_trusted=True)
        self.assertEqual(receive(self.core,v).action,'DELIVER')
        self.assert_reject('SESSION_REPLAY',receive,self.core,v)
        # Signed hop with wrong immutable hash also cannot advance the floor.
        c=core_for(v);self.addCleanup(c.journal.close)
        frame=decode(good[14:],PROFILE);body=bytearray(frame.body);body[-160]^=1
        body[-64:]=signing(3).sign(b'IPvX-BCP/0.2/hop\0'+frame.header+bytes(body[-208:-64]))
        self.assert_reject('AUTH_FAILED',c.receive,good[:14]+frame.header+bytes(body),now=NOW,monotonic=MONO,clock_trusted=True)
        self.assertEqual(receive(c,v).action,'DELIVER')

    def test_complete_handshake_and_restart_drops_sessions(self):
        view=state();a=Core(PROFILE,1,bytes.fromhex('020000000001'),view,Journal());b=Core(PROFILE,3,bytes.fromhex('020000000003'),view,Journal())
        self.addCleanup(a.journal.close);self.addCleanup(b.journal.close)
        hello=decode(bytes.fromhex(BY_ID['V01-HELLO']['bcp_hex']),PROFILE)
        challenge=decode(bytes.fromhex(BY_ID['V02-CHALLENGE']['bcp_hex']),PROFILE)
        confirm=decode(bytes.fromhex(BY_ID['V03-CONFIRM']['bcp_hex']),PROFILE)
        a.sent_hello(hello,MONO)
        self.assertEqual(receive(b,BY_ID['V01-HELLO']).action,'PENDING_CHALLENGE')
        b.sent_challenge(challenge,MONO)
        self.assertEqual(receive(a,BY_ID['V02-CHALLENGE']).action,'CONFIRM_SESSION')
        revoked=Core(PROFILE,1,a.local_mac,state({'node_overrides':{'3':{'status':2}},
            'latest_checkpoint':BY_ID['N16-REVOKED']['assumptions']['latest_checkpoint']}),Journal())
        self.addCleanup(revoked.journal.close)
        revoked._challenges=dict(a._challenges)
        self.assert_reject('KEY_REVOKED',revoked.sent_confirm,confirm,MONO,NOW,clock_trusted=True)
        self.assertEqual(revoked._sessions,{})
        a.sent_confirm(confirm,MONO,NOW,clock_trusted=True)
        self.assertEqual(receive(b,BY_ID['V03-CONFIRM']).action,'ADMIT_SESSION')
        self.assertEqual(receive(b,BY_ID['V06-DATA-A-R']).action,'FORWARD')
        restarted=Core(PROFILE,3,b.local_mac,view,b.journal)
        self.assert_reject('AUTH_FAILED',receive,restarted,BY_ID['V06-DATA-A-R'])

    def test_unsolicited_expired_or_changed_handshake_rejected(self):
        c=Core(PROFILE,1,bytes.fromhex('020000000001'),state(),self.core.journal)
        self.assert_reject('AUTH_FAILED',receive,c,BY_ID['V02-CHALLENGE'])
        hello=decode(bytes.fromhex(BY_ID['V01-HELLO']['bcp_hex']),PROFILE);c.sent_hello(hello,MONO)
        self.assert_reject('AUTH_FAILED',receive,c,BY_ID['V02-CHALLENGE'],monotonic=MONO+6)

    def test_route_cache_local_expiry_and_revocation(self):
        c=core_for(BY_ID['V05-ROUTE-SUFFIX']);self.addCleanup(c.journal.close)
        receive(c,BY_ID['V05-ROUTE-SUFFIX'])
        self.assertEqual(len(c.routes(now=NOW,monotonic=MONO+4,clock_trusted=True)),1)
        self.assertEqual(c.routes(now=NOW,monotonic=MONO+6,clock_trusted=True),[])
        c.state=state(BY_ID['N18-EDGE-REVOKED']['assumptions'])
        self.assertEqual(c.routes(now=NOW,monotonic=MONO+1,clock_trusted=True),[])
        self.assert_reject('TIME_UNTRUSTED',c.routes,now=NOW,monotonic=MONO+1,clock_trusted=False)

    def test_truncations_and_bounded_random_bytes_never_crash_parser(self):
        raw=bytes.fromhex(BY_ID['V07-DATA-R-B']['bcp_hex'])
        for size in range(len(raw)):
            with self.assertRaises(Reject): decode(raw[:size],PROFILE)
        rng=random.Random(20261031)
        for _ in range(500):
            raw=rng.randbytes(rng.randrange(1600))
            with self.assertRaises(Reject): decode(raw,PROFILE)
        original=bytes.fromhex(BY_ID['V07-DATA-R-B']['bcp_hex'])
        for _ in range(1000):
            raw=bytearray(original);raw[rng.randrange(len(raw))]^=rng.randrange(1,256)
            try:decode(bytes(raw),PROFILE)
            except Reject:pass

    def test_reserved_bytes_profile_and_uint_bounds(self):
        for n in (-1,2**64,True):
            with self.assertRaises(ValueError):uint(n,8)
        raw=bytearray(bytes.fromhex(BY_ID['V07-DATA-R-B']['bcp_hex']));raw[44+355]=1
        self.assert_reject('NONCANONICAL',decode,bytes(raw),PROFILE)
        with self.assertRaises(TypeError):decode(bytes.fromhex(BY_ID['V07-DATA-R-B']['bcp_hex']),PROFILE).fields['traffic']=7

    def test_mtu_exactly_1500_and_one_byte_over(self):
        v=BY_ID['V11-DATA-MTU-1500'];c=core_for(v);self.addCleanup(c.journal.close)
        self.assertEqual(receive(c,v).action,'FORWARD')
        self.assertEqual(len(bytes.fromhex(v['bcp_hex'])),1500)
        raw=bytes.fromhex(v['bcp_hex'])+b'x'
        self.assert_reject('PACKET_TOO_LARGE',decode,raw,PROFILE)

    def test_inactive_reverse_policy_cannot_authorize_receipts(self):
        v=BY_ID['V12-RECEIPT-ACCEPTED-R-A'];c=core_for(v);self.addCleanup(c.journal.close)
        latest=c.state.latest;rule=next(p.rule for p in latest.connections.values() if p.source==2)
        policies=dict(latest.connections);policies[rule]=replace(policies[rule],status=2)
        c.state=replace(c.state,latest=replace(latest,connections=policies))
        self.assert_reject('POLICY_DENIED',receive,c,v)

    def test_invalid_decrypted_receipt_fields_rejected(self):
        for fault in ('phase','reserved','hash','linkage','trailing'):
            with self.subTest(fault=fault):
                v=BY_ID['V12-RECEIPT-ACCEPTED-R-A'];c=core_for(v);self.addCleanup(c.journal.close)
                old=decode(bytes.fromhex(v['bcp_hex']),PROFILE);f=old.fields;view=c.state.packet
                plain=bytearray(bytes.fromhex(v['plaintext_hex']))
                if fault=='phase':plain[96]=3
                if fault=='reserved':plain[97]=1
                if fault=='hash':plain[106]^=1
                if fault=='linkage':plain[32]^=1
                if fault=='trailing':plain+=b'x'
                frame=build.packet(PROFILE,6,f['checkpoint'],view.nodes[2],view.nodes[1],view.connections[f['rule']],f['message'],
                    f['packet'],bytes(plain),f['path'],f['edges'],f['session'],1,1,signing(2),signing(3),encryption(1).public_key(),
                    issued=NOW,expires=NOW+60,request_hash=f['request_hash'])
                self.assert_reject('INVALID_PAYLOAD',c.receive,
                    ethernet(c.local_mac,bytes.fromhex('020000000003'),frame.encode()),now=NOW,monotonic=MONO,clock_trusted=True)

    def test_unknown_registry_enum_and_untrusted_attestation(self):
        v=BY_ID['V07-DATA-R-B']
        for change in ('enum','string_attestation'):
            c=core_for(v);self.addCleanup(c.journal.close)
            if change=='enum':
                s=c.state.latest;nodes=dict(s.nodes);nodes[1]=replace(nodes[1],status=9)
                c.state=replace(c.state,latest=replace(s,nodes=nodes))
            else:c.state=replace(c.state,attestation=replace(c.state.attestation,authenticated='true'))
            self.assert_reject('STATE_UNAVAILABLE',receive,c,v)

    def test_session_epoch_binding_even_with_same_signing_key(self):
        v=BY_ID['V07-DATA-R-B'];f=decode(bytes.fromhex(v['bcp_hex']),PROFILE).fields
        s=self.core._sessions[f['session']]
        self.core._sessions[f['session']]=replace(s,initiator_epoch=0)
        self.assert_reject('KEY_REVOKED',receive,self.core,v)

    def test_route_ranking_uses_total_contract_cost(self):
        v=BY_ID['V05-ROUTE-SUFFIX'];c=core_for(v);self.addCleanup(c.journal.close)
        receive(c,v);short=decode(bytes.fromhex(v['bcp_hex']),PROFILE);f=short.fields
        path=(3,4,5,6,7,8,2);s=c.state.packet
        edges=tuple((e.rule,e.version) for a,b in zip(path,path[1:]) for e in s.edges.values() if (e.source,e.destination)==(a,b))
        longer=build.route(PROFILE,f['session'],2,f['checkpoint'],b'n'*32,NOW,NOW+30,
            tuple((n,s.nodes[n].epoch) for n in path),edges,[signing(n) for n in path],signing(3))
        c.receive(ethernet(c.local_mac,bytes.fromhex('020000000003'),longer.encode()),now=NOW,monotonic=MONO,clock_trusted=True)
        self.assertEqual([x.fields['path'] for x in c.routes(now=NOW,monotonic=MONO,clock_trusted=True)],[(3,2),path])

    def test_control_burst_limit_and_hello_rate(self):
        v=BY_ID['V04-ROUTE-ORIGIN'];c=core_for(v);self.addCleanup(c.journal.close)
        f=decode(bytes.fromhex(v['bcp_hex']),PROFILE).fields
        for sequence in range(1,33):
            frame=build.route(PROFILE,f['session'],sequence,f['checkpoint'],f['nonce'],f['issued'],f['expires'],
                              f['nodes'],f['edges'],[signing(2)],signing(2))
            c.receive(ethernet(c.local_mac,bytes.fromhex('020000000002'),frame.encode()),now=NOW,monotonic=MONO,clock_trusted=True)
        self.assert_reject('POLICY_DENIED',c.receive,
            ethernet(c.local_mac,bytes.fromhex('020000000002'),frame.encode()),now=NOW,monotonic=MONO,clock_trusted=True)
        c=core_for(BY_ID['V01-HELLO']);self.addCleanup(c.journal.close)
        receive(c,BY_ID['V01-HELLO'])
        self.assert_reject('POLICY_DENIED',receive,c,BY_ID['V01-HELLO'],monotonic=MONO+0.5)


class Persistence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=str(Path(self.tmp.name)/'journal.sqlite3');self.j=Journal(self.path);self.addCleanup(lambda:self.j.close())
        self.c=state().packet.checkpoint

    def test_checkpoint_conflict_latches_across_restart(self):
        self.j.checkpoint(self.c)
        with self.assertRaisesRegex(Reject,'STATE_CONFLICT'):
            self.j.checkpoint(replace(self.c,block_hash=b'x'*32))
        self.j.close();self.j=Journal(self.path)
        with self.assertRaisesRegex(Reject,'STATE_CONFLICT'):self.j.checkpoint(self.c)

    def test_new_checkpoint_requires_explicit_ancestry_and_no_rollback(self):
        self.j.checkpoint(self.c)
        newer=replace(self.c,number=2,block_hash=b'n'*32)
        with self.assertRaisesRegex(Reject,'STATE_UNAVAILABLE'):self.j.checkpoint(newer)
        self.j.checkpoint(newer,True)
        with self.assertRaisesRegex(Reject,'STATE_CONFLICT'):self.j.checkpoint(self.c)

    def test_delivery_dedup_survives_reopen_and_conflict(self):
        self.assertEqual(self.j.deliver(1,b'm'*32,b'h'*32),'NEW')
        self.j.close();self.j=Journal(self.path)
        self.assertEqual(self.j.deliver(1,b'm'*32,b'h'*32),'DUPLICATE')
        with self.assertRaisesRegex(Reject,'MESSAGE_CONFLICT'):self.j.deliver(1,b'm'*32,b'x'*32)

    def test_receipts_complete_first_accepted_then_complete_and_error(self):
        for message in (b'a'*32,b'b'*32):
            self.j.remember_request(1,2,message,digest(b'request'),b'request')
        self.j.receipt(1,2,b'a'*32,digest(b'request'),1,b'')
        for message in (b'a'*32,b'b'*32):
            self.j.receipt(1,2,message,digest(b'request'),2,b'result')
            self.j.receipt(1,2,message,digest(b'request'),1,b'')
            self.j.receipt(1,2,message,digest(b'request'),0,b'',18)
            self.j.receipt(1,2,message,digest(b'request'),2,b'result')
            with self.assertRaisesRegex(Reject,'MESSAGE_CONFLICT'):
                self.j.receipt(1,2,message,digest(b'request'),2,b'changed')
        with self.assertRaisesRegex(Reject,'UNKNOWN'):
            self.j.receipt(1,2,b'u'*32,digest(b'request'),2,b'result')
        with self.assertRaisesRegex(Reject,'INVALID_PAYLOAD'):
            self.j.receipt(1,3,b'a'*32,digest(b'request'),2,b'result')
