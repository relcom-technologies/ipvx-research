from copy import deepcopy
import importlib.util
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bcp_net_plan_readiness',HERE/'readiness.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        denied=AssertionError('Only static plan checks are allowed')
        for target in ('create_connection','getaddrinfo'):patch.object(socket,target,side_effect=denied).start()
        patch.object(socket.socket,'connect',side_effect=denied).start()
        patch.object(subprocess,'Popen',side_effect=denied).start()
        self.plan,self.stand,self.evidence,self.candidate=(r.load(name) for name in ('protocol.json','stand.json','evidence-contract.json','candidate.json'))

    def errors(self):return r.validate(self.plan,self.stand,self.evidence,self.candidate)

    def test_proposed_package_is_valid_but_not_ready_or_executed(self):
        self.assertEqual(self.errors(),[])
        value=r.evaluate();self.assertTrue(value['plan_valid']);self.assertFalse(value['ready_to_request_launch'])
        self.assertFalse(value['ready_to_launch']);self.assertFalse(value['execution_performed'])
        self.assertIn('separate_owner_launch_decision_missing',value['missing'])
        self.assertGreaterEqual(len(value['missing']),15)

    def test_direct_bypass_or_ip_tunnel_invalidates_only_path(self):
        self.stand['links'].append({'id':'L3','kind':'vxlan','ends':['A:a0','B:b0']})
        self.assertIn('veth_only',self.errors());self.assertIn('sole_path',self.errors())

    def test_bridge_addresses_and_loopback_cannot_be_hidden(self):
        self.stand['data_plane']['bridges']=['host'];self.stand['data_plane']['ipv4_addresses']=['assigned']
        self.stand['data_plane']['loopback_up']=True
        self.assertIn('no_external_path',self.errors());self.assertIn('no_ip_configuration',self.errors())

    def test_shared_router_mac_or_core_context_is_rejected(self):
        ports=self.stand['nodes'][1]['ports'];ports[1]['mac']=ports[0]['mac']
        self.stand['process_policy']['relay_core_contexts']=1
        self.assertIn('separate_port_macs',self.errors());self.assertIn('relay_control_binding',self.errors())

    def test_all_keys_route_helper_and_old_keys_are_not_allowed(self):
        self.plan['route_constraints']['offline_all_keys_route_constructor_allowed']=True
        self.plan['state_constraints']['old_vector_seeds_as_run_keys']=True
        self.assertIn('distributed_signing_requirement',self.errors());self.assertIn('fixture_keys_time',self.errors())

    def test_live_rpc_and_transaction_claim_cannot_be_inferred(self):
        self.stand['fixture_provider']['live_rpc']=True;self.plan['state_constraints']['real_chain_finality_tested']=True
        self.plan['transactions_performed']=True
        self.assertIn('no_live_chain',self.errors());self.assertIn('no_chain_claim',self.errors());self.assertIn('no_operations',self.errors())

    def test_capture_must_cover_link_up_without_filter_or_drops(self):
        self.stand['setup_policy']['capture_before_link_up']=False;self.evidence['capture']['filter']='ether proto 0x88b5'
        self.evidence['capture']['drops_max']=1
        self.assertIn('setup_capture_cleanup',self.errors());self.assertIn('capture_contract',self.errors())

    def test_missing_oracles_or_incomplete_evidence_cannot_pass(self):
        self.plan['cases'][0]['oracle']='';self.evidence['mandatory_per_run'].remove('journals')
        self.plan['capture_drop_action']='PASS'
        self.assertIn('case_oracles',self.errors());self.assertIn('evidence_coverage',self.errors());self.assertIn('no_false_pass',self.errors())

    def test_case_identity_and_unknown_outcome_are_preserved(self):
        self.plan['cases'][-1]['id']=self.plan['cases'][0]['id'];self.plan['outcomes'].remove('INCONCLUSIVE')
        self.assertIn('case_coverage',self.errors());self.assertIn('outcomes',self.errors())

    def test_results_and_independence_cannot_be_invented(self):
        self.plan['results']={'pass':True};self.plan['execution_performed']=True
        self.stand['physical_ethernet_claim']=True;self.stand['independent_operator_claim']=True
        self.assertIn('not_run',self.errors());self.assertIn('claim_limits',self.errors())

    def test_scope_changes_when_components_or_window_change_but_not_ack(self):
        original=r.scope_hash(self.candidate)
        other=deepcopy(self.candidate);other['owner_scope_ack']={'scope_sha256':original,'evidence':'declaration'}
        self.assertEqual(original,r.scope_hash(other))
        other['components']['af_packet_transport']['sha256']='1'*64
        self.assertNotEqual(original,r.scope_hash(other))
        other=deepcopy(self.candidate);other['accepted_window']={'start':'proposed','end':'proposed'}
        self.assertNotEqual(original,r.scope_hash(other))

    def test_retry_time_and_resource_expansion_require_new_review(self):
        self.plan['limits']['attempts_per_id_max']=4;self.stand['resources']['active_seconds_max']=3600
        self.stand['resources']['models']=1
        self.assertIn('retry_bounds',self.errors());self.assertIn('runtime_storage_bounds',self.errors());self.assertIn('no_paid_resources',self.errors())

    def test_process_policy_cannot_gain_admin_or_payload_channel(self):
        self.stand['process_policy']['deny_host_net_admin']=False
        self.stand['process_policy']['control_payloads_allowed']=True
        self.assertIn('process_isolation',self.errors());self.assertIn('relay_control_binding',self.errors())

    def test_source_pins_and_physical_limits_remain_explicit(self):
        errors,count=r.pinned_sources();self.assertEqual(errors,[]);self.assertGreaterEqual(count,84)
        profile=r.ROOT/'docs/proposals/bcp-0.2/profile.json'
        import json
        constants=json.loads(profile.read_text())['constants']
        self.assertEqual(self.stand['data_plane']['bcp_payload_mtu'],constants['mtu'])
        self.assertEqual(self.plan['limits']['attempt_timeout_seconds'],constants['attempt_timeout_seconds'])

if __name__=='__main__':unittest.main()
