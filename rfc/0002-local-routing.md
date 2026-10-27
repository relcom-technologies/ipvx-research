# RFC-0002 — Bounded native routing

Status: Draft · not an IETF RFC.

## Implemented baseline
Each admitted router exchanges signed path vectors only with its fixed neighbors. It chooses the next hop locally, avoids paths containing itself and expires failed neighbors. The observer reads evidence and does not select routes or forward tasks. Native task packets and route advertisements travel in Ethernet frames, not IP packets.

The demonstrated topology has primary A–R1–B and alternate A–R2–R3–B. The documented outage closes R1's data-plane socket; it is not a power-off of the host. Current limits: 16 members, four neighbors and seven hops, on controlled Ethernet links under one operator.

## What has not been established
Global routing scalability, WAN interconnection without an IP underlay, autonomous open admission, NAT traversal, multi-operator trust, incentives, congestion control or attack resistance. The larger model assumes compact advertisements and a longer hop budget that the implementation does not yet provide.

## Proposed next research
Compare hierarchical locators, path-vector state and content/capability discovery separately. Measure convergence, control-plane bytes and queue saturation before increasing limits. Specify a congestion and fragmentation strategy. Document any inter-site IP tunnel as an IP underlay, not native delivery without IP.

## Acceptance evidence
Repeated multi-host failover, loop tests, bounded state and byte accounting, malicious advertisement rejection, independent implementation and at least two administratively independent sites. Majority approval is required before adopting a replacement protocol.
