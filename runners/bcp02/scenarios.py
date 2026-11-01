"""Declared controls only; no frames, request bytes or model output cross control pipes."""
from .common import CASES

# Wait conditions use observations, never drive payload forwarding. Detailed
# success remains the independent archived capture/journal verifier's decision.
SCRIPTS={
 'P01':[('A','PROBE'),('WAIT','P01')],
 'P02':[('A','PROBE'),('WAIT','P02')],
 'N01':[('A','PROBE'),('WAIT','N01')],
 'N02':[('STOP','R'),('BARRIER','R_STOPPED'),('A','PROBE'),('WAIT','N02')],
 'N03':[('A','PROBE'),('WAIT','N03')],
 'N04':[('A','PROBE'),('WAIT','N04')],
 'N05':[('A','PROBE'),('WAIT','N05')],
 'N06':[('A','PREPARE'),('ALL','ROTATE'),('A','PROBE'),('WAIT','N06')],
 'N07-forward':[('A','PREPARE'),('ALL','DENY_FORWARD'),('A','PROBE'),('WAIT','N07-forward')],
 'N07-reverse':[('A','PROBE'),('WAIT','REVERSE_PREPARED'),('ALL','DENY_REVERSE'),('B','PROBE'),('WAIT','N07-reverse')],
 'N08':[('ALL','UNAVAILABLE'),('ALL','STALE'),('WAIT','N08')],
 'N09':[('A','PROBE'),('WAIT','N09-first'),('STOP','B'),('RESTART','B'),('A','RETRY'),
        ('WAIT','N09-before'),('B','HANDSHAKE'),('WAIT','N09-route'),('A','RETRY'),('WAIT','N09')],
 'N10':[('A','PROBE'),('WAIT','N10')],
 'N11':[('A','PROBE'),('WAIT','N11')],
}


def observed(events,condition):
    def found(node=None,decision=None,reject=None,disposition=None,kind=None):
        return [e for e in events if (node is None or e.get('node')==node)
                and (decision is None or e.get('decision')==decision)
                and (reject is None or e.get('reject_code')==reject)
                and (disposition is None or e.get('disposition')==disposition)
                and (kind is None or e.get('kind')==kind)]
    done=lambda n:len({e['message_id'] for e in found('A','COMPLETED')})>=n
    reject=lambda n,c:bool(found(n,'REJECT',c))
    if condition=='ROUTES':return bool(found('A','CACHE_ROUTE') and found('B','CACHE_ROUTE'))
    if condition in ('P01','P02'):return done(10 if condition=='P01' else 1) and (condition!='P01' or bool(found('A','DELIVER',kind=7)))
    if condition=='N01':return reject('A','PACKET_TOO_LARGE')
    if condition=='N02':return len(found('A','UNKNOWN'))==10
    if condition=='N03':return reject('R','AUTH_FAILED') and done(1)
    if condition=='N04':return reject('R','SESSION_REPLAY') and done(1)
    if condition=='N05':return bool(found('B','DELIVER',disposition='DUPLICATE')) and done(1)
    if condition=='N06':return bool(found('R','REJECT','KEY_REVOKED',kind=5))
    if condition in ('N07-forward','N07-reverse'):return bool(found('R','REJECT','POLICY_DENIED',kind=5 if condition.endswith('forward') else 6))
    if condition=='REVERSE_PREPARED':return bool(found('B','REVERSE_PREPARED'))
    if condition=='N08':return reject('A','STATE_UNAVAILABLE') and reject('A','STATE_STALE')
    if condition=='N09-first':return done(1)
    if condition=='N09-before':return reject('B','AUTH_FAILED')
    if condition=='N09-route':return bool(found('B','CACHE_ROUTE'))
    if condition=='N09':return reject('B','AUTH_FAILED') and bool(found('B','DELIVER',disposition='DUPLICATE'))
    if condition=='N10':return done(1) and reject('A','UNKNOWN') and len(found('A','REJECT','MESSAGE_CONFLICT'))>=2
    if condition=='N11':return bool(found('B','WORKER_GAP_UNKNOWN') and found('A','UNKNOWN')) and not found('A','COMPLETED')
    raise ValueError('unknown observation condition')
