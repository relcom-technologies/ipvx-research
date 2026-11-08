"""Read-only planning checks. Never creates a stand or grants launch rights."""
from hashlib import sha256
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SCOPE_FILES=('README.md','protocol.json','stand.json','evidence-contract.json','source-pins.json',
             'readiness.py','checks.py','preserve.py','tests/test_plan.py')
COMPONENTS=frozenset(('namespace_launcher_cleanup','af_packet_transport','two_interface_relay_binding',
  'peer_signed_route_suffix_assembler','fixture_state_key_exporter','bounded_scheduler_worker',
  'capture_verifier','environment_clock_preflight'))
EVIDENCE=frozenset(('scope_sha256','run_manifest','source_binary_dataset_hashes','namespace_interface_inventory',
  'process_capability_and_socket_policy','clock_health','pcap','capture_statistics','events','journals',
  'payload_manifest','worker_log','state_bank','injection_manifest','fault_barrier','result','SHA256SUMS'))


def load(name):
    def pairs(items):
        value={}
        for k,v in items:
            if k in value:raise ValueError('duplicate JSON key')
            value[k]=v
        return value
    return json.loads((HERE/name).read_text(),object_pairs_hook=pairs)


def scope_hash(candidate):
    value={'files':{name:sha256((HERE/name).read_bytes()).hexdigest() for name in SCOPE_FILES},
        'components':candidate['components'],'window':candidate['accepted_window'],'run_id':candidate['run_id'],
        'preflight':[candidate['host_preflight_receipt'],candidate['process_isolation_receipt'],candidate['dataset_receipt']]}
    return sha256(b'IPVX-BCP02-NET-001-F/0.1\0'+json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate(plan,stand,evidence,candidate):
    errors=[]
    def need(ok,name):
        if not ok:errors.append(name)
    need(plan['protocol_id']==candidate['protocol_id']=='IPVX-BCP02-NET-001-F' and plan['version']==candidate['version']=='0.1','identity')
    need(plan['wire_version']=='0.2' and plan['source_base']=='f467f7ebeb7a2fe8ed108ba6f906fd966735f1a0','version_pin')
    need(plan['state_mode']==stand['fixture_provider']['mode']=='fixture-state-ethernet','fixture_scope')
    need(plan['results'] is None and plan['execution_performed'] is False and stand['network_created'] is False,'not_run')
    need(candidate['run_started'] is False,'candidate_not_run')
    need(plan['transactions_performed'] is False and plan['production_actions'] is False and stand['setup_policy']['modify_production'] is False,'no_operations')
    state=plan['state_constraints'];provider=stand['fixture_provider']
    need(state['live_rpc'] is provider['live_rpc'] is provider['on_chain_deployments'] is False,'no_live_chain')
    need(state['real_chain_finality_tested'] is state['real_contract_addresses_assigned'] is False,'no_chain_claim')
    need(state['old_vector_seeds_as_run_keys'] is state['time_patch_in_baseline'] is False and state['public_fixture_marker_required'] is True,'fixture_keys_time')
    need((state['max_state_age_seconds'],state['clock_skew_seconds'])==(1800,5),'state_constants')
    need(stand['host']['count']==1 and plan['roles']['operator_count']==1 and plan['roles']['node_processes']==3,'role_scope')
    nodes={n['id']:n for n in stand['nodes']}
    need(set(nodes)=={'A','R','B'} and [nodes[n]['nft'] for n in ('A','R','B')]==[1,3,2],'nodes')
    need([nodes[n]['role'] for n in ('A','R','B')]==['endpoint','router','endpoint'] and len({n['namespace'] for n in nodes.values()})==3,'role_namespace_binding')
    ports={n['id']+':'+p['name']:p for n in stand['nodes'] for p in n['ports']}
    need(set(ports)=={'A:a0','R:r0','R:r1','B:b0'},'port_scope')
    need(len({p['mac'] for p in ports.values()})==4,'separate_port_macs')
    need({name:p['link'] for name,p in ports.items()}=={'A:a0':'L1','R:r0':'L1','R:r1':'L2','B:b0':'L2'},'port_link_binding')
    links={l['id']:l for l in stand['links']}
    need(set(links)=={'L1','L2'} and all(l['kind']=='veth' for l in links.values()),'veth_only')
    need({k:tuple(v['ends']) for k,v in links.items()}=={'L1':('A:a0','R:r0'),'L2':('R:r1','B:b0')},'sole_path')
    data=stand['data_plane']
    need((data['socket_family'],data['socket_type'],data['ethertype_hex'],data['bcp_payload_mtu'],data['ethernet_header_bytes'])==('AF_PACKET','SOCK_RAW','88b5',1500,14),'wire_binding')
    need(all(data[k]==[] for k in ('bridges','physical_peers','ip_tunnels','ipv4_addresses','ipv6_addresses','routes')),'no_external_path')
    need(all(data[k] is False for k in ('vlan','loopback_up','ipv6_autoconfiguration','ip_forwarding')),'no_ip_configuration')
    policy=stand['process_policy'];setup=stand['setup_policy']
    need(set(policy['deny_socket_families'])=={'AF_INET','AF_INET6'} and policy['deny_setns'] is True and policy['deny_host_net_admin'] is True,'process_isolation')
    need(policy['node_capabilities']==['CAP_NET_RAW in own namespace only'],'capability_scope')
    need(all(policy[k] is True for k in ('bound_ifindex_required','drop_packet_outgoing','detect_truncation','own_private_key_only','one_relay_event_loop')),'transport_requirements')
    need(policy['relay_core_contexts']==2 and policy['control_payloads_allowed'] is False,'relay_control_binding')
    need(all(setup[k] is True for k in ('create_only_new_objects','abort_on_name_collision','interfaces_initially_down','disable_autoconfiguration_before_link_up','capture_before_link_up','full_capture_before_first_hello','record_namespace_inode_and_peer_ifindex','teardown_after_evidence_archival')),'setup_capture_cleanup')
    need(setup['capture_filter'] is None and setup['capture_drops_allowed']==0,'unfiltered_capture')
    route=plan['route_constraints']
    need(route['shared_peer_private_keys'] is route['offline_all_keys_route_constructor_allowed'] is False and route['peer_signed_suffix_required'] is True,'distributed_signing_requirement')
    need(set(map(tuple,route['directed_edges']))=={(1,3),(3,1),(3,2),(2,3)} and set(map(tuple,route['directed_connections']))=={(1,2),(2,1)},'directed_permissions')
    lim=plan['limits'];res=stand['resources']
    need((lim['attempts_per_id_max'],lim['attempt_timeout_seconds'],lim['data_per_session_inflight'])==(3,5,1),'retry_bounds')
    need(0<lim['logical_requests_max']<=40 and 0<lim['data_attempts_max']<=120 and lim['fault_outcome_deadline_seconds']==20,'traffic_bounds')
    need(0<res['active_seconds_max']<=1200 and 0<res['wall_seconds_max']<=3600 and 0<res['capture_bytes_max']<=268435456 and 0<res['artifact_bytes_max']<=1073741824,'runtime_storage_bounds')
    need(0<res['vcpu_max']<=2 and 0<res['ram_mib_max']<=4096 and 0<res['disk_mib_max']<=10240,'host_resource_bounds')
    need(all(res[k]==0 for k in ('models','gpu','paid_calls','blockchain_transactions')),'no_paid_resources')
    need(lim['retention_seconds_min']>=604800 and evidence['private_retention_seconds_min']>=604800,'retention')
    cases=plan['cases'];ids=[c['id'] for c in cases]
    need(len(ids)==len(set(ids))==13 and set(ids)=={'P01','P02',*(f'N{i:02}' for i in range(1,12))},'case_coverage')
    need(all(c['oracle'] and c['success_metric'] and c['stimulus'] and 'pcap' in c['evidence'] and 'events' in c['evidence'] for c in cases),'case_oracles')
    need(plan['pass_requires_all_cases'] is True and plan['unexpected_ethertype_action']=='FAIL_ISOLATION_AND_STOP' and plan['capture_drop_action']=='INCONCLUSIVE_AND_STOP','no_false_pass')
    need(set(plan['outcomes'])=={'NOT_RUN','BLOCKED','PASS','FAIL_PROTOCOL','FAIL_ISOLATION','INCONCLUSIVE','ABORTED'},'outcomes')
    need(set(evidence['mandatory_per_run'])==EVIDENCE,'evidence_coverage')
    capture=evidence['capture']
    need(capture['filter'] is None and capture['all_ethertypes'] is capture['full_snaplen'] is capture['capture_starts_before_hello'] is capture['capture_starts_before_link_up'] is True and capture['drops_max']==0 and set(capture['links'])=={'L1','L2'} and capture['expected_ethertype_hex']==data['ethertype_hex'],'capture_contract')
    need(evidence['missing_evidence_result']=='INCONCLUSIVE' and evidence['result_observed'] is None and evidence['old_evidence_reissued'] is False and evidence['source_hash_authenticates_identity'] is False,'evidence_limits')
    need(all(stand[k] is False for k in ('whole_device_no_ip_claim','physical_ethernet_claim','independent_operator_claim')) and plan['roles']['independent_operator_confirmed'] is False,'claim_limits')
    need(set(candidate['components'])==COMPONENTS,'implementation_components')
    return errors


def pinned_sources():
    # Since 2026-11-08 only pins inside the runner's source scope are verified; workflows and
    # downloads outside it may change. The scope is read as JSON from the runner manifest.
    from fnmatch import fnmatchcase
    scope=json.loads((ROOT/'runners/bcp02/manifest.json').read_text())['scope']
    pins=load('source-pins.json');errors=[];verified=0
    if pins['source_base']!='f467f7ebeb7a2fe8ed108ba6f906fd966735f1a0':errors.append('source_base_mismatch')
    for name,expected in pins['files'].items():
        if not any(fnmatchcase(name,g) for g in scope):continue
        relative=Path(name);path=ROOT/relative
        if relative.is_absolute() or '..' in relative.parts or path.resolve()!=path or not name.startswith(('bcp/','tests/bcp/','adapters/','integration/','contracts/','docs/proposals/','data/downloads/','.github/workflows/')):
            errors.append('unsafe_source_path');continue
        if sha256(path.read_bytes()).hexdigest()!=expected:errors.append('source_hash_mismatch:'+name)
        else:verified+=1
    return errors,verified


def evaluate():
    plan,stand,evidence,candidate=(load(name) for name in ('protocol.json','stand.json','evidence-contract.json','candidate.json'))
    errors=validate(plan,stand,evidence,candidate);source_errors,count=pinned_sources();errors+=source_errors
    digest=scope_hash(candidate);missing=[]
    for name,component in sorted(candidate['components'].items()):
        if not all(component.get(k) for k in ('revision','sha256','review_evidence','offline_validation_receipt')):missing.append('component:'+name)
    if not stand['host']['allocated'] or not candidate['resources_allocated'] or not stand['host']['operator'] or not stand['host']['resource_authority_evidence']:missing.append('host_resources_operator_not_assigned')
    if not all(stand['host'].get(k) for k in ('image_sha256','kernel_release','kernel_config_sha256')) or not all(stand['binary_pins'].values()):missing.append('environment_binary_pins_missing')
    for name in ('host_preflight_receipt','process_isolation_receipt','dataset_receipt','accepted_window','run_id'):
        if not candidate.get(name):missing.append(name+':missing')
    if not stand['fixture_provider']['run_dataset_sha256']:missing.append('fixture_dataset_sha256_missing')
    ack=candidate['owner_scope_ack']
    if not isinstance(ack,dict) or ack.get('scope_sha256')!=digest or not ack.get('evidence'):missing.append('owner_frozen_scope_ack_missing')
    if not candidate['owner_launch_decision']:missing.append('separate_owner_launch_decision_missing')
    return {'protocol_id':plan['protocol_id'],'scope_sha256':digest,'plan_valid':not errors,'errors':errors,
        'source_files_verified':count,'ready_to_request_launch':not errors and not missing,
        'ready_to_launch':False,'missing':missing,'execution_performed':False,
        'interpretation':'Declared planning gates only, not authenticated authority. This read-only tool never grants or performs launch.'}


if __name__=='__main__':print(json.dumps(evaluate(),indent=2))
