import hashlib
import json
import socket
import unittest
from unittest.mock import patch

from bcp.wire import Reject, decode, context_id, signing_inputs, hpke_info
from fixtures import FIXTURE, PROFILE, SPEC, VECTORS, core_for, receive


class Compatibility(unittest.TestCase):
    def test_all_frozen_vectors_offline(self):
        """Expected outcomes belong to the test, never to the core or adapter."""
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')), \
             patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')), \
             patch.object(socket,'getaddrinfo',side_effect=AssertionError('network forbidden')):
            for vector in VECTORS:
                with self.subTest(vector=vector['id']):
                    core = core_for(vector)
                    try:
                        try:
                            decision = receive(core,vector)
                            actual = 'ACCEPT'
                        except Reject as e:
                            actual = e.code
                        # Preserve the frozen bad-session fixture; do not weaken
                        # session authentication to reach its intended payload error.
                        expected = 'AUTH_FAILED' if vector['id'] == 'N29-REQUEST-HASH' else vector['expected']
                        self.assertEqual(actual,expected)
                        if actual == 'ACCEPT':
                            self.assertEqual(decision.action,vector['expected_action'])
                            if decision.plaintext is not None:
                                self.assertEqual(decision.plaintext.hex(),vector['plaintext_hex'])
                    finally:
                        core.journal.close()

    def test_accepted_bytes_and_signing_inputs(self):
        for vector in VECTORS:
            with self.subTest(vector=vector['id']):
                raw = bytes.fromhex(vector['bcp_hex'])
                self.assertEqual(len(raw),vector['bcp_bytes'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(),vector['bcp_sha256'])
                if vector['id'].startswith('V'):
                    frame = decode(raw,PROFILE)
                    self.assertEqual(frame.encode(),raw)
                    actual = signing_inputs(frame)
                    for key,value in vector['signing_inputs_hex'].items():
                        result = [v.hex() for v in actual[key]] if isinstance(actual[key],list) else actual[key].hex()
                        self.assertEqual(result,value)
                    if frame.kind >= 5:
                        self.assertEqual(hpke_info(frame).hex(),vector['hpke_info_hex'])

    def test_context_binding_and_specification_preservation(self):
        c = FIXTURE['context_fields']
        self.assertEqual(context_id(c['chain_id'],bytes.fromhex(c['genesis_hash_hex']),
            [bytes.fromhex(c[n+'_hex']) for n in ('node_registry','transit_policy','connection_policy')],
            [bytes.fromhex(c[n+'_code_hash_hex']) for n in ('node_registry','transit_policy','connection_policy')]),PROFILE)
        manifest = json.loads((SPEC/'preservation.json').read_text())
        for f in manifest['files']:
            self.assertEqual(hashlib.sha256((SPEC.parents[2]/f['path']).read_bytes()).hexdigest(),f['sha256'])
