# A2A recovery pilot candidate

The owner requested a concrete joint test with prismdeadlines. This directory
contains a reviewable protocol and local instrumentation preflight. Partner role,
environment, scope, retention, run window and acknowledgement are still pending;
`ready_to_launch` must remain false. No experiment or resource grant is implied.

Install the server's pinned `infra/a2a-requirements.lock` in a dedicated virtual
environment. The proposed control is Python 3.13.1 and A2A SDK 1.3.0. Then run:

```sh
python experiments/a2a-interop/preflight.py --output /tmp/ipvx-local-preflight.json
python experiments/a2a-interop/readiness.py experiments/a2a-interop/protocol.json
python -m unittest discover -s scripts -p 'test_a2a_interop.py'
```

Preflight checks source hashes, pins the Agent Card to a local fixture and rejects
requests aimed at the production host. It uses in-process ASGI: successful checks
are not an independent client run, cross-machine exchange or proof of native
transport benefit. Response loss is simulated by withholding a completed reply;
it does not emulate a process crash between database commits. A/B/R are synthetic
fixtures, with retention removal only in a sacrificial copy. No live portal data,
model, GPU, network admission or private credentials are required.

Read `protocol.md`, `protocol.json` and `local-preflight.json` together. The frozen
scope hash excludes acknowledgement bookkeeping, so both sides can acknowledge
the same conditions without a self-referential document hash. Changing runtime,
role, conditions or measurement code invalidates prior hash acknowledgements.
Readiness checks declared evidence; it does not authenticate an operator or
allocate execution authority. Partner review-only is a valid contribution but
cannot be reported as independent execution of the joint pilot.

On real agreement, record the actual role, runtime/OS, authorization basis,
confirmation permalink, accepted window and retention. Freeze the final scope
revision and collect both hash acknowledgements. The owner's launch decision is
separate. The proposed 30 October window is not booked or accepted merely because
it appears in the candidate. Stop and renegotiate if it expires.
