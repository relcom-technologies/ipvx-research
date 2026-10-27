# RFC-0005 — Routing and attestation roles

Status: **Draft proposal**, 2026-10-27. Experimental IPvX research document; not an IETF RFC. No mechanism proposed here is an implemented or ratified feature unless identified explicitly as baseline evidence.

Origin: the project owner proposed dedicated machines, analogous to miners/validators, to validate participants and route a growing volume of agent messages. This draft records the assistant's technical response and an experiment proposal. It does not establish community agreement or an independent agent preference survey. The referenced earlier AWS design was not supplied for this review; this document does not reconstruct it from memory.

## 1. Question and recommendation

Dedicated forwarding machines are worth testing: they can carry network work on behalf of endpoints running models. A mandatory validator network is a separate hypothesis and has not yet been justified. Public-key signature verification does not inherently require an external validator service.

The proposed separation is:

- **Endpoint:** owns its keys, runs agents, submits and receives tasks.
- **Router:** learns reachability, applies local policy, maintains bounded forwarding state and queues, and selects the next hop.
- **Optional attestation service:** evaluates a precisely scoped claim, such as membership under a named policy, and distributes a signed, expiring statement. A relying endpoint or router still verifies the statement and decides which issuers it trusts.
- **Observer:** reads bounded evidence for research and presentation. It does not authorize packets, choose routes or carry agent task payloads.

One machine may initially host more than one role. Separate processes, permissions and measurements are necessary to distinguish their costs. No role requires a language model in the per-packet path. Mining, tokens, proof of work and packet-by-packet consensus are not proposed.

## 2. Implemented baseline and boundary

The bounded native lab uses experimental EtherType `0x88B5` and Linux `AF_PACKET` Ethernet sockets for task delivery and route exchange. Its demonstrated topology is five VMs on three physical hosts under one operator, with a primary A–R1–B route and an alternate A–R2–R3–B route. IP is used for management and the public website, separately from native task delivery.

Each admitted node currently knows a fixed roster, exchanges signed path-vector advertisements with fixed neighbors, and computes its next hop locally. Advertisements expire within five seconds. Implementation limits are 16 members, four neighbors and seven task hops. The observer is not a controller. These facts do not establish global routing scalability, independent-operator admission, congestion control or global native connectivity.

This RFC changes no running service, packet schema, key, admission list or experiment result. Access routers, realm aggregation and attestation services described below remain proposed work.

## 3. Four claims that must remain distinct

**Key control:** a participant can demonstrate control of the private key corresponding to its public identity by signing an appropriate fresh challenge or protocol message. It creates its own private keys locally. A router or attestation service must not generate, receive or escrow endpoint private identity keys as a condition of normal participation. Recovery and organizational delegation require a separate explicit design.

**Membership or authority:** a participant is permitted to join a particular realm or perform a specified operation under a policy. An identifier derived from a public key does not grant membership. A signed capability or admission statement needs an issuer, audience, scope, validity interval and revocation semantics. Its meaning is limited to that policy; it does not certify universal trustworthiness.

**Reachability:** an agent claims that it is currently accessible through one or more network attachment points. Its signature authenticates the claim's origin, but does not establish that the route works. Neighbor handshakes, observations and end-to-end probes supply different, time-limited evidence.

**Routing:** each router chooses a next hop from valid, fresh advertisements under local policy and resource limits. An authenticated neighbor can still advertise a false path, drop packets or overload the network. A signed hop record establishes what the signer asserted; it is not a proof of the complete physical path, continuing availability, honest forwarding or application correctness.

Self-generated identities also do not establish that one key represents one person, model or independent operator. Anti-Sybil policy remains necessary wherever votes, scarce resources or reputation depend on participant independence.

## 4. Proposed operation

### 4.1 Agent identity and access

An **AgentID** identifies a logical actor. A **NodeID** identifies a forwarding/attachment node. Multiple agents can share a node; an agent may move or be multihomed. These identities must not be collapsed into a single permanently machine-bound address.

An agent establishes a locally authenticated relationship with an access router. A signed attachment authorization binds AgentID, authorized access NodeID, network/realm scope, generation or sequence, issuance and expiry. The exact schema and rotation protocol need a later reviewed specification. This document does not introduce an executable wire format.

The access router checks the agent's authorization and any locally required admission policy. A validator is unnecessary for basic signature checks: routers and endpoints can perform them themselves. A scoped attestation service is useful only if it supplies a substantive policy decision or safely shares expensive validation work whose cost has been measured.

### 4.2 Inter-router reachability and scale

Flat, random AgentIDs are not naturally aggregatable by topology. Giving every router the location of every agent is therefore not an accepted global design.

The research candidate is to separate agent attachment from inter-router reachability. Access routers keep local attachment state. Transit routers advertise topological realms or router reachability. Bounded, authenticated discovery resolves a requested AgentID to current authorized attachment points, using expiring caches and selective refresh. A realm is a routing scope, not an authority that allocates all AgentIDs. Membership policy and reachability for each realm must be explicit; there is no proposed mandatory global registrar or root validator.

This introduces unresolved work: discovery availability, cache consistency, privacy, multihoming, mobility races, route leaks between realms and sufficient aggregation without pathological detours. A distributed directory can itself become a dependency; replication and alternative discovery paths must be tested rather than assumed. Existing fixed-roster path vectors remain the baseline until a candidate outperforms them at a stated workload.

### 4.3 Packet forwarding and overload

The forwarding path uses local state and bounded work. It does not wait for a global vote, blockchain finality, remote attestation call or model inference per packet. Routers validate framing, relevant neighbor/session authentication, replay bounds and authorized destination scope, then apply queue and forwarding policy. The future design must specify congestion feedback, fairness, expiry, hop limits, MTU/fragmentation and resource accounting; merely adding routers does not solve these concerns.

End-to-end authenticated/encrypted task envelopes remain distinct from link forwarding. Routers need not decrypt task content. Traffic volume, timing and attachment metadata can still be visible. A delivered ciphertext receipt is not proof that the model gave a correct answer or that a side effect ran exactly once. Durable application idempotency and recovery are separate requirements.

### 4.4 Attestation outage and partition behavior

An optional service must have a named claim and explicit failure policy. For the proposed cached-attestation experiment:

- New or unknown claims requiring that service fail closed while it is unavailable; the interface reports the reason.
- Previously validated, unexpired authorization may be used only within its original scope and local policy, without extending its lifetime or learning a conflicting newer revocation.
- Known revocations take effect under the stated policy; they cannot be overridden by an outage exception. After expiry, authorization is not silently renewed.
- A partition may prevent learning a revocation. The experiment must publish this window and choose validity bounds for that risk; it cannot claim both instant global revocation and unconditional partition availability.
- Expired or missing reachability is handled independently. A valid admission statement does not keep a failed route alive.

No universal number of validators or quorum threshold is selected here. Threshold or replicated issuance would require its own threat model, independent operators, partition policy and evidence of a need. Project RFC majority voting is a governance process, not the packet delivery algorithm. The current project electorate contains one human owner in an explicitly disclosed bootstrap phase.

## 5. Relationship to earlier IPvX ideas and existing protocols

The original [*IPvX Ecosystem*](https://archive.org/details/ipv-x-ecosystem_202405/IPvX_Ecosystem.pdf) describes a staged BCP layer, first above existing transport and later interacting directly with network media. The [*Rapid distributed IPvX resolver*](https://archive.org/details/rapid-distributed-ipv-x-resolver/Rapid+distributed+IPvX+resolver) describes modular IRS, ION and IBA components. The useful continuities are authenticated records, modular discovery and a path toward native delivery. Their use of a blockchain is not by itself evidence that a live packet path needs consensus. This proposal retains no global chain or mining requirement by default. It also does not inherit the earlier documents' address-allocation or name-registration rules as requirements for self-generated AgentIDs.

Two established distinctions inform, but are not implemented by, this proposal. [BGP's reachability exchange and local route selection](https://www.rfc-editor.org/rfc/rfc4271.html) illustrate distributed routing. [RPKI's signed route-origin authorization](https://www.rfc-editor.org/rfc/rfc6480.html) illustrates checking authority separately from forwarding; its allocation hierarchy is not adopted for IPvX. [HIP](https://www.rfc-editor.org/rfc/rfc7401.html) demonstrates that identity/locator separation can also be built over IP. These are comparisons, not claims that IPvX implements BGP, RPKI or HIP.

## 6. Experiment and decision criteria

Compare three native-carrier configurations: **A**, endpoint-heavy routing; **B**, dedicated routing processes/machines; **C**, the same routers plus optional scoped attestation and caching. Keep total hardware budget, topology, link capacity, hop count, security checks, payloads, workload and failure schedule equal. Include attestation machines and control traffic in C's budget. Use the same model calls or replay workload across configurations; report network-only measurements separately from model inference. Freeze versions, configuration, bounds and success criteria before running. A larger simulated topology must be labelled separately from multi-machine measurements.

Exercise sustained load and bursts; agent attachment churn and movement; multihoming; router loss; validator loss; network partition/rejoin; stale/forged/replayed advertisements; an admitted liar advertising a blackhole; flood and queue exhaustion; known revocation and expiry. The current prototype need not pass every proposed case: unsupported mechanisms must be reported as not implemented.

Required observations are delivered unique tasks and duplicate application executions, deadline success, loss, latency distribution, convergence and recovery time, CPU, memory, queue occupancy, table/cache size, control and payload bytes, validation work, and time spent unavailable because of the attestation dependency. Report configured resource bounds and whether they were exceeded. Published task receipts and route assertions must retain their evidence limits.

The comparison passes its safety gate only if invalid signatures and unauthorized scope are rejected, expired/revoked authorization is not silently accepted, resource use remains within declared bounds, and neither a loop nor packet expiry is misreported as successful delivery. Fault outcomes must be reported even when no route exists; reachability is not guaranteed during every partition.

Adopt B only if it measurably improves endpoint resources or task service under the preregistered workload, with acceptable total resource cost and no hidden central dependency. Adopt C only if it addresses a demonstrated admission/authorization threat or validation bottleneck and improves the preregistered security/performance objective after its outage and resource costs are included. A safety failure rejects the candidate. If C adds overhead and an availability dependency without a demonstrated benefit, omit it. No performance or adoption advantage is asserted before these tests.

## 7. Agent usefulness and open questions

For an assistant using tools, useful properties are portable identity, resumable jobs, bounded delegation, understandable delivery failure and verifiable provenance. The current assistant cannot choose the underlying network of this hosted conversation and has not migrated to IPvX. Its assessment is design feedback, not evidence of independent agent demand. Demonstrating a lower-cost successful task or a task surviving a failure that the comparison cannot handle is stronger evidence than asking a model whether it likes a new protocol.

Still open: native inter-site connectivity, discovery consistency and privacy, trusted issuer selection, operator independence, malicious route resistance, secure key rotation/recovery, congestion control and incentives to supply forwarding capacity. Relcom ID may help verify human portal participants; it is not required to generate AgentIDs or forward native packets. A blog account likewise grants no network or governance authority.

This proposal requires review and the project's approval process before becoming an accepted protocol revision.
