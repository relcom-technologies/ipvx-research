"""Explicit public projection of a privately verified strict-OS experiment.

No recursive copying: signed proofs contain infrastructure addresses and stay private.
Run the laboratory verifier first. This exporter is not a substitute for it.
"""
import argparse
import hashlib
import json
from pathlib import Path


def project(root):
    summary_bytes = (root / 'verified-summary.json').read_bytes()
    summary = json.loads(summary_bytes)
    if summary['status'] != 'measured':
        raise ValueError('Complete verified comparison required')
    result = {k: summary[k] for k in ('schema_version', 'status', 'source_revision', 'model_sha256', 'answer_comparison', 'limits')}
    result.update(workflow='https://github.com/relcom-technologies/relcom-infra/actions/runs/40563118803',
                  model='Qwen3-0.6B Q8_0', summary_sha256=hashlib.sha256(summary_bytes).hexdigest(),
                  modes={}, tasks=[], deliveries=[], inferences=[], nodes={}, adapter_transmissions=0)
    for mode in ('native', 'ip'):
        result['modes'][mode] = {k: summary['modes'][mode][k] for k in (
            'echo', 'task', 'inference', 'correct_decisions', 'tasks', 'signed_deliveries',
            'capture_frames', 'verified_link_envelopes')}
        result['modes'][mode]['captures'] = [{k: capture[k] for k in (
            'frames', 'ethertypes', 'verified_link_envelopes',
            'incomplete_rpc_assemblies', 'pcap_sha256')} for capture in summary['modes'][mode]['captures']]
    for run in ('round1-native', 'round2-native'):
        record = json.loads((root / (run + '.json')).read_text())
        for name, node in record['nodes'].items():
            files = node['files']
            public = record['roster'][name]['payload']
            result['nodes'][name] = {k: public[k] for k in ('id', 'public_key')}
            if 'deliveries.jsonl' in files:
                for line in files['deliveries.jsonl'].splitlines():
                    delivery = json.loads(line)
                    result['deliveries'].append({k: delivery[k] for k in (
                        'message_id', 'case', 'phase', 'bytes', 'elapsed_ms', 'attempts', 'path')})
            if name == 'A':
                for line in files['results.jsonl'].splitlines():
                    task = json.loads(line)
                    result['tasks'].append({k: task[k] for k in (
                        'case', 'claim', 'expected', 'final', 'decision_correct', 'elapsed_ms')})
            if 'inferences.jsonl' in files:
                for line in files['inferences.jsonl'].splitlines():
                    inference = json.loads(line)
                    result['inferences'].append(dict(node=name, run=run, **{k: inference[k] for k in (
                        'case', 'phase', 'elapsed_ms', 'parsed', 'usage', 'prompt_sha256')}))
            adapter = json.loads((root / run / name / 'adapter-summary.json').read_text())
            result['adapter_transmissions'] += adapter['out']
    result['correct_decisions'] = summary['modes']['native']['correct_decisions']
    result['frame_observations'] = summary['modes']['native']['capture_frames']
    result['limits'] += [
        'Control uses the same application hops A–R–B over TCP/IP; this is not direct IP or kernel-only routing.',
        'Raw captures and signed hop objects retain infrastructure addresses and remain private. This public projection cannot independently re-verify their original bytes.',
        'Guest UTC is initialized from a local read-only host virtual device; no guest IP time client. Timings use monotonic clocks.',
        'Fixed three-key admission, two CPU models and four cases per mode do not establish Internet scale or autonomous network adoption.'
    ]
    result['verification'] = 'Private offline verification checked original frame bytes, signatures, signed receipts, stable IDs, model hashes, whole guest kernel probes and restoration. Public aliases are a projection of that result.'
    if len(result['tasks']) != 4 or len(result['deliveries']) != 48:
        raise ValueError('Unexpected measured record count')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_results', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(project(args.private_results), ensure_ascii=False, indent=2) + '\n')
