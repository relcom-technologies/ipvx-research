"""Default is read-only NOT_RUN. Explicit `run` reaches gated Linux setup; `rehearse` only the permit-free rehearsal."""
import argparse
import json
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from .admission import authorize, source_hash
from .common import Blocked


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command')
    sub.add_parser('check')
    v=sub.add_parser('verify');v.add_argument('directory',type=Path)
    r=sub.add_parser('run');r.add_argument('--permit',required=True);r.add_argument('--output',required=True,type=Path);r.add_argument('--dataset',required=True,type=Path)
    d=sub.add_parser('prepare-dataset');d.add_argument('--run-id',required=True);d.add_argument('--output',required=True,type=Path)
    h=sub.add_parser('rehearse');h.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.command in (None,'check'):
        print(json.dumps(dict(state_mode='fixture-state-ethernet',outcome='NOT_RUN',scope_sha256=source_hash(),
            ready_to_launch=False,network_created=False,transactions=0,reason='Separate implementation review, host pins, owner scope ACK and launch permit required.'),indent=2));return
    if args.command=='prepare-dataset':
        from .fixture import export
        from .dataset import seal
        from .common import run_id
        import time
        scope=source_hash()
        identifier=run_id(args.run_id);now=int(time.time())
        export(args.output,identifier,now)
        print(json.dumps(dict(outcome='PREPARED_NOT_AUTHORIZED',scope_sha256=scope,
            dataset=seal(args.output,time.time()),launch_permit_issued=False,ready_to_launch=False),indent=2));return
    if args.command=='verify':
        from .verifier import evaluate
        print(json.dumps(evaluate(args.directory),indent=2));return
    if args.command=='rehearse':
        from .rehearsal import rehearse
        try:report=rehearse(args.output)
        except Blocked as e:
            print(json.dumps(dict(outcome='BLOCKED',network_created=False,reason=str(e))))
            raise SystemExit(2)
        print(json.dumps(report,indent=2))
        raise SystemExit(0 if report['outcome']=='REHEARSAL_PASS' else 1)
    started=False
    try:
        permit,config=authorize(args.permit)
        from .controller import Controller
        started=True
        result=Controller(args.output.resolve(),permit,config,args.permit,args.dataset).run_all()
        print(json.dumps(result,indent=2))
    except (Blocked,ValueError,OSError,KeyError,InvalidSignature) as e:
        print(json.dumps(dict(outcome='ABORTED' if started else 'BLOCKED',network_created=None if started else False,reason=str(e))))
        raise SystemExit(2)


if __name__=='__main__':main()
