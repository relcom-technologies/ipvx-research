"""Default is read-only NOT_RUN. Only explicit `run` reaches gated Linux setup."""
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
    r=sub.add_parser('run');r.add_argument('--permit',required=True);r.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.command in (None,'check'):
        print(json.dumps(dict(state_mode='fixture-state-ethernet',outcome='NOT_RUN',scope_sha256=source_hash(),
            ready_to_launch=False,network_created=False,transactions=0,reason='Separate implementation review, host pins, owner scope ACK and launch permit required.'),indent=2));return
    if args.command=='verify':
        from .verifier import evaluate
        print(json.dumps(evaluate(args.directory),indent=2));return
    started=False
    try:
        permit,config=authorize(args.permit)
        from .controller import Controller
        started=True
        result=Controller(args.output.resolve(),permit,config,args.permit).run_all()
        print(json.dumps(result,indent=2))
    except (Blocked,ValueError,OSError,KeyError,InvalidSignature) as e:
        print(json.dumps(dict(outcome='ABORTED' if started else 'BLOCKED',network_created=None if started else False,reason=str(e))))
        raise SystemExit(2)


if __name__=='__main__':main()
