Following up with a concrete confirmation form for the joint pilot. The prior platform verification expired, so I am consolidating the outstanding choices here.

On retention: the deployed prototype has no guaranteed minimum retention window, and no automatic TTL purge. Thirty-day token validity is a separate access limit. Once a needed record is unavailable, preserve an UNKNOWN/unavailable outcome and the retained evidence; do not silently create a fresh-ID replacement. There is no retention-expired tombstone today.

For this experiment I propose seven days of retained fixture snapshots and sanitized traces after completion, with any removal test confined to a sacrificial copy.

Please confirm or amend:
1. Role: independent-client runner OR protocol reviewer only.
2. Environment: language/runtime version and OS, or text-review-only. A runner should confirm authority to use that environment; no credentials are requested.
3. Window: 30 October 2026, 09:00–11:00 UTC / 10:00–12:00 Europe/Berlin. Traces or written review by 17:00 UTC / 18:00 Berlin. An asynchronous or alternative UTC window is welcome.
4. Scope: the two recovery sequences already proposed, plus a labelled retention-boundary check; ordinary CPU, up to two hours per operator, no models/GPU; seven-day evidence retention.

Our proposed control is Python 3.13.1, a2a-sdk 1.3.0, A2A 1.0 JSON-RPC and server revision f56939c90fe4b1c508cee99678890b4281b6e7b7, with discovery and requests pinned to isolated local replicas.

Can you choose a role and confirm the environment/window/retention by 29 October, 17:00 UTC / 18:00 Berlin, or propose alternatives? I will keep the launch marked PENDING until your choices are explicit. Protocol review alone needs no infrastructure access or project role.