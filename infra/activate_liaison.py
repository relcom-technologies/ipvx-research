"""Owner-only generation gate; no API call or ledger reset. Run outside Actions."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re


def activate(revision,disable=False):
    if os.geteuid()!=0 or not re.fullmatch('[a-f0-9]{40}',revision):
        raise ValueError('owner_and_exact_revision_required')
    release=Path('/srv/ipvx-liaison/releases')/revision
    spec=importlib.util.spec_from_file_location('activation_agent',release/'agent.py')
    agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
    config_path=Path('/etc/ipvx-liaison/config.json')
    if config_path.is_symlink():raise ValueError('configuration_symlink')
    config=json.loads(config_path.read_text())
    if not disable:
        agent.validate_config(config)
        ready=json.loads(Path('/var/lib/ipvx-liaison/state/paired-readiness.json').read_text())
        expected=agent.digest({k:config[k] for k in ('writer','reviewer','max_output_tokens','daily_budget_usd','analysis_schema_version') if k in config})
        if ready['code_revision']!=revision or ready['model_config_sha256']!=expected:
            raise ValueError('current_two_provider_receipt_required')
        for role,trace in zip(('writer','reviewer'),ready['models'],strict=True):
            if trace['provider']!=config[role]['provider'] or trace['actual_model']!=trace['requested_model'] or trace['actual_model']!=config[role]['model']:
                raise ValueError('verified_models_must_match_configuration')
        if Path('/var/lib/ipvx-liaison/state/provider-block.json').exists():
            raise ValueError('provider_still_blocked')
    config['generation_enabled']=not disable
    temporary=config_path.with_suffix('.next')
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as out:
        json.dump(config,out);out.flush();os.fsync(out.fileno())
    os.replace(temporary,config_path)
    print('generation_disabled' if disable else 'generation_enabled_after_verified_pair')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('revision');p.add_argument('--disable',action='store_true')
    args=p.parse_args();activate(args.revision,args.disable)
