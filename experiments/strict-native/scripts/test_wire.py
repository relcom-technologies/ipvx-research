"""Synthetic parser tests only. These never create a guest-run receipt."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

spec=importlib.util.spec_from_file_location('xns_verify',Path(__file__).with_name('verify.py'))
verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)


class WireParser(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate()
        public=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        other=Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.keys={1:{'public_key':public.hex(),'node_id':hashlib.sha256(public).hexdigest()},
                   2:{'public_key':other.hex(),'node_id':hashlib.sha256(other).hexdigest()}}
        self.body=bytearray(188+1024);self.body[:8]=b'XNS1\x01\x01\x03\x00'
        self.body[8:24]=struct.pack('!IIIHH',1,1,2,1024,0)
        self.body[28:60]=hashlib.sha256(public).digest();self.body[60:92]=hashlib.sha256(other).digest()
        self.body[92:124]=public
        self.body[188:]=bytes((31+i*17)&255 for i in range(1024))
        signed=bytearray(self.body);signed[6]=0
        self.body[124:188]=self.key.sign(bytes(signed));self.crc()

    def crc(self):
        self.body[24:28]=bytes(4)
        self.body[24:28]=struct.pack('!I',zlib.crc32(self.body))

    def ethernet(self,kind=0x88b5):
        return bytes(12)+struct.pack('!H',kind)+self.body

    def test_valid_signed_fixture(self):
        record=verify.frame_record(self.ethernet(),self.keys)
        self.assertEqual(record['sequence'],1)
        self.assertEqual(record['bytes'],1212)

    def test_changed_payload_with_recomputed_crc_is_not_authenticated(self):
        self.body[188]^=1;self.crc()
        with self.assertRaises(InvalidSignature):verify.frame_record(self.ethernet(),self.keys)

    def test_mutable_hop_remains_bounded(self):
        self.body[6]=2;self.crc()
        self.assertEqual(verify.frame_record(self.ethernet(),self.keys)['hop_limit'],2)
        self.body[6]=0;self.crc()
        with self.assertRaises(ValueError):verify.frame_record(self.ethernet(),self.keys)

    def test_all_ip_arp_and_vlan_inner_types_fail(self):
        for kind in (0x0800,0x0806,0x86dd):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):verify.frame_record(self.ethernet(kind),self.keys)
                vlan=bytes(12)+struct.pack('!HHH',0x8100,7,kind)+self.body
                with self.assertRaises(ValueError):verify.frame_record(vlan,self.keys)

    def test_classic_full_pcap_and_truncation(self):
        packet=self.ethernet()
        global_header=struct.pack('<IHHIIII',0xa1b2c3d4,2,4,0,0,65535,1)
        record=struct.pack('<IIII',1,0,len(packet),len(packet))+packet
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'synthetic.pcap';path.write_bytes(global_header+record)
            self.assertEqual(list(verify.packets(path)),[packet])
            path.write_bytes(global_header+record[:-1])
            with self.assertRaises(ValueError):list(verify.packets(path))


if __name__=='__main__':unittest.main()
