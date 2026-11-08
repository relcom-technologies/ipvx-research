"""Synthetic signatures, temp bundles and mocked controller only; no launch."""
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch, Mock

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from runners.bcp02.admission import PERMIT_DOMAIN, verify_permit, authorize
from runners.bcp02.common import Blocked, read_json, sha, private_json
from runners.bcp02.dataset import seal, load, fresh, snapshot, inspect_public, actor_key
from runners.bcp02.fixture import export
from runners.bcp02.tests.memory import T0

SCOPE = 'a'*64
NOW = T0+100


def signed(binding, *, key=None, **updates):
    key = key or Ed25519PrivateKey.generate()
    payload = dict(version=2,scope_sha256=SCOPE,run_id=binding['run_id'],host_image_sha256='b'*64,
                   not_before=binding['created_at'],not_after=binding['created_at']+500,
                   launch=True,transactions=0,production=False,dataset=binding)
    payload.update(updates)
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    doc=dict(payload=base64.b64encode(raw).decode(),signature=base64.b64encode(key.sign(PERMIT_DOMAIN+raw)).decode())
    return doc,key.public_key().public_bytes_raw().hex()


class DatasetAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.base=Path(cls.temp.name).resolve()/'dataset'
        export(cls.base,'offline-admission-tests',NOW);cls.binding=seal(cls.base,NOW)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def copy(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        p=Path(t.name).resolve()/'copy';shutil.copytree(self.base,p);return p

    def verify(self,binding=None,now=NOW,**updates):
        doc,key=signed(binding or self.binding,**updates)
        return verify_permit(doc,key,scope=SCOPE,now=now)

    def test_valid_signature_binds_sealed_bytes_run_and_lifetime(self):
        p=self.verify();contents=load(self.base,p['dataset'],NOW)
        self.assertEqual(sha(contents['dataset.json']),self.binding['dataset_sha256'])
        self.assertEqual(sha(contents['bundle.json']),self.binding['bundle_sha256'])
        self.assertLessEqual(self.binding['expires_at'],NOW+1800)
        self.assertLess(self.binding['expires_at'],NOW+1800) # oldest checkpoint, not a relabeled time

    def test_payload_change_after_signature_fails(self):
        doc,key=signed(self.binding);raw=json.loads(base64.b64decode(doc['payload']));raw['dataset']['dataset_sha256']='0'*64
        doc['payload']=base64.b64encode(json.dumps(raw).encode()).decode()
        with self.assertRaises(InvalidSignature):verify_permit(doc,key,scope=SCOPE,now=NOW)

    def test_old_permit_domain_cannot_be_reused(self):
        doc,key=signed(self.binding);sk=Ed25519PrivateKey.generate();raw=base64.b64decode(doc['payload'])
        doc['signature']=base64.b64encode(sk.sign(b'IPVX BCP02 isolated run permit\0'+raw)).decode()
        with self.assertRaises(InvalidSignature):verify_permit(doc,sk.public_key().public_bytes_raw().hex(),scope=SCOPE,now=NOW)

    def test_v1_payload_or_missing_dataset_is_rejected(self):
        for change in ({'version':1},{'dataset':None}):
            with self.subTest(change=change),self.assertRaises(Blocked):self.verify(**change)

    def test_signed_other_source_or_run_is_rejected(self):
        for change in ({'scope_sha256':'f'*64},{'run_id':'offline-other-run'}):
            with self.subTest(change=change),self.assertRaises(Blocked):self.verify(**change)

    def test_signed_window_cannot_outlive_dataset(self):
        with self.assertRaisesRegex(Blocked,'lifetime'):self.verify(not_after=self.binding['expires_at']+1)
        with self.assertRaises(Blocked):self.verify(not_before=NOW-1)

    def test_expiry_is_exclusive_and_future_input_is_rejected(self):
        fresh(self.binding,self.binding['expires_at']-0.001)
        for now in (NOW-0.001,self.binding['expires_at'],self.binding['expires_at']+1,float('nan')):
            with self.subTest(now=now),self.assertRaises(Blocked):fresh(self.binding,now)

    def test_oversized_or_noninteger_freshness_is_rejected(self):
        for update in ({'max_state_age_seconds':1801},{'expires_at':NOW+1801},{'created_at':True}):
            with self.subTest(update=update),self.assertRaises(Blocked):fresh({**self.binding,**update},NOW)

    def test_missing_pin_or_infinite_permit_window_is_rejected(self):
        for binding in ({k:v for k,v in self.binding.items() if k!='bundle_sha256'}, {**self.binding,'dataset_sha256':'g'*64}):
            with self.assertRaises(Blocked):self.verify(binding)
        with self.assertRaises(Blocked):self.verify(not_after=float('inf'))

    def test_json_payload_bytes_are_pinned_not_reencoded(self):
        p=self.copy();f=p/'dataset.json';f.write_bytes(f.read_bytes()+b'\n')
        with self.assertRaisesRegex(Blocked,'bytes changed'):load(p,self.binding,NOW)

    def test_relabeling_creation_time_cannot_renew_a_permit(self):
        p=self.copy();f=p/'dataset.json';d=json.loads(f.read_text());d['created_at']+=1;f.write_text(json.dumps(d))
        with self.assertRaises(Blocked):load(p,self.binding,NOW+1)

    def test_replaced_member_manifest_or_key_fails(self):
        for name in ('bank.json','bundle.json','A/key.json'):
            with self.subTest(name=name):
                p=self.copy();f=p/name;f.write_bytes(f.read_bytes()+b' ')
                with self.assertRaises(Blocked):load(p,self.binding,NOW)

    def test_alternate_sealed_bundle_needs_its_own_signature(self):
        p=self.copy();f=p/'bank.json';d=json.loads(f.read_text());d['warning']='different bytes';f.write_text(json.dumps(d))
        data=json.loads((p/'dataset.json').read_text());data['bank']=d;(p/'dataset.json').write_text(json.dumps(data))
        (p/'bundle.json').unlink();other=seal(p,NOW)
        self.assertNotEqual(other['bundle_sha256'],self.binding['bundle_sha256'])
        with self.assertRaises(Blocked):load(p,self.binding,NOW)

    def test_symlink_hardlink_fifo_and_permissions_are_rejected(self):
        for kind in ('symlink','hardlink','fifo','world-readable'):
            with self.subTest(kind=kind):
                p=self.copy();f=p/'A/key.json'
                if kind=='world-readable':f.chmod(0o644)
                else:
                    f.unlink()
                    if kind=='symlink':f.symlink_to(self.base/'A/key.json')
                    elif kind=='hardlink':os.link(self.base/'A/key.json',f)
                    else:os.mkfifo(f,0o600)
                try:
                    with self.assertRaises((Blocked,OSError)):load(p,self.binding,NOW)
                finally:
                    if kind=='hardlink':f.unlink()

    def test_extra_member_or_directory_is_rejected(self):
        for name in ('extra.json','other-dir'):
            p=self.copy()
            if name.endswith('json'):private_json(p/name,{})
            else:(p/name).mkdir(mode=0o700)
            with self.assertRaises(Blocked):load(p,self.binding,NOW)

    def test_snapshot_uses_validated_bytes_despite_later_input_mutation(self):
        p=self.copy();contents=load(p,self.binding,NOW);(p/'dataset.json').write_text('{}')
        dest=p.parent/'snapshot';snapshot(contents,dest)
        self.assertEqual(load(dest,self.binding,NOW),contents)
        self.assertEqual((dest/'dataset.json').stat().st_mode&0o777,0o600)

    def test_child_reads_only_public_state_and_its_own_key(self):
        from runners.bcp02 import dataset as api
        real=api.read_private;seen=[]
        def read(path):seen.append(str(Path(path).relative_to(self.base)));return real(path)
        with patch.object(api,'read_private',side_effect=read):
            data,manifest=inspect_public(self.base,self.binding,NOW)
            key=actor_key(self.base/'A/key.json','A',data,manifest)
        self.assertEqual(key['nft'],1)
        self.assertEqual(set(seen),{'bundle.json','dataset.json','A/key.json'})
        with self.assertRaises(Blocked):actor_key(self.base/'B/key.json','A',data,manifest)

    def test_invalid_bundle_blocks_controller_before_claim_or_setup(self):
        from runners.bcp02.controller import Controller
        p=self.copy();(p/'dataset.json').write_text('{}');permit=self.verify();config={}
        with patch('runners.bcp02.controller.selectors.DefaultSelector'),\
             patch('runners.bcp02.controller.preflight',return_value={}),\
             patch('runners.bcp02.controller.authorize',return_value=(permit,config)),\
             patch('runners.bcp02.controller.claim_once') as claim,patch('time.time',return_value=NOW):
            c=Controller(p.parent/'output',permit,config,'/unit-permit',p);c.stand=Mock()
            with self.assertRaises(Blocked):c.run_all()
            claim.assert_not_called();c.stand.create.assert_not_called();self.assertFalse(c.directory.exists())

    def test_controller_bounds_reject_expiry_before_network_poll(self):
        from runners.bcp02.controller import Controller
        permit=self.verify()
        with patch('runners.bcp02.controller.selectors.DefaultSelector'),patch('time.time',return_value=NOW):
            c=Controller(self.base,permit,{},'/unit-permit',self.base)
        with patch('time.time',return_value=self.binding['expires_at']):
            with self.assertRaises(Blocked):c.bounds()

    def test_child_rejects_changed_dataset_before_packet_sockets(self):
        from runners.bcp02 import entry
        p=self.copy();(p/'dataset.json').write_text('{}');permit=self.verify()
        config=dict(namespace_inode=77,run_id=permit['run_id'],dataset=str(p/'dataset.json'),dataset_sha256=self.binding['dataset_sha256'],role='capture')
        path=p.parent/'child.json';private_json(path,config)
        real=os.stat
        def stat(path,*a,**kw):return Mock(st_ino=77) if str(path)=='/proc/self/ns/net' else real(path,*a,**kw)
        with patch.object(entry.sys,'argv',['entry',str(path),'permit']),patch.object(entry,'authorize',return_value=(permit,{})),\
             patch.object(entry.os,'stat',side_effect=stat),patch.object(entry,'PacketPort') as sockets,patch('time.time',return_value=NOW):
            with self.assertRaises(Blocked):entry.main()
            sockets.assert_not_called()

    def test_expired_child_is_blocked_before_opening_sockets(self):
        from runners.bcp02 import entry
        p=self.copy();permit=self.verify()
        config=dict(namespace_inode=77,run_id=permit['run_id'],dataset=str(p/'dataset.json'),dataset_sha256=self.binding['dataset_sha256'],role='capture')
        path=p.parent/'child.json';private_json(path,config);real=os.stat
        def stat(path,*a,**kw):return Mock(st_ino=77) if str(path)=='/proc/self/ns/net' else real(path,*a,**kw)
        with patch.object(entry.sys,'argv',['entry',str(path),'permit']),patch.object(entry,'authorize',return_value=(permit,{})),\
             patch.object(entry.os,'stat',side_effect=stat),patch.object(entry,'PacketPort') as sockets,\
             patch('time.time',side_effect=[NOW,self.binding['expires_at']]):
            with self.assertRaisesRegex(Blocked,'expired'):entry.main()
            sockets.assert_not_called()

    def test_reviewed_config_must_match_exact_signed_dataset(self):
        from types import SimpleNamespace
        p=self.copy().parent/'permit.json';doc,key=signed(self.binding);private_json(p,doc)
        c=dict(state_mode='fixture-state-ethernet',owner_public_key=key,review_evidence='unit-only',
               host_image_sha256='b'*64,kernel_config_sha256='c'*64,binary_sha256={'python':'d'*64},
               allocated_host={'unit_only':True},accepted_window=[NOW,NOW+500],owner_scope_ack='unit-only',
               owner_launch_decision='UNIT TEST ONLY',resources_allocated=True,run_dataset=self.binding)
        ls=Path.lstat;st=Path.stat
        def fake_ls(path,*a,**kw):
            real=ls(path,*a,**kw)
            return SimpleNamespace(st_uid=0,st_mode=real.st_mode,st_size=real.st_size) if path==p else real
        def fake_st(path,*a,**kw):
            real=st(path,*a,**kw)
            return SimpleNamespace(st_uid=0,st_mode=real.st_mode) if path==p.parent else real
        with patch.object(Path,'lstat',fake_ls),patch.object(Path,'stat',fake_st),\
             patch('runners.bcp02.admission.source_hash',return_value=SCOPE):
            self.assertEqual(authorize(p,config=c,now=NOW)[0]['dataset'],self.binding)
            other=deepcopy(c);other['run_dataset']['expires_at']-=1
            with self.assertRaisesRegex(Blocked,'reviewed configuration'):authorize(p,config=other,now=NOW)

    def test_committed_config_has_no_dataset_or_owner_authority(self):
        from runners.bcp02.admission import HERE
        config=read_json(HERE/'launch-config.json')
        self.assertIsNone(config['run_dataset']);self.assertIsNone(config['accepted_window'])
        self.assertIsNone(config['owner_launch_decision'])
        with self.assertRaisesRegex(Blocked,'launch decision'):authorize('/unused')


if __name__=='__main__':unittest.main()
