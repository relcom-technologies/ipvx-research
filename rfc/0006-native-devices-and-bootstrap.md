# RFC-0006 — Native devices, offline bootstrap and explicit trust

Status: **Draft proposal**, 2026-10-27. Experimental IPvX project document; not an IETF RFC. Not ratified, not a claim of deployed hardware or a globally interoperable protocol.

Origin: the owner clarified that the next target is an entire participating node OS without TCP/IP, using ordinary physical devices, its own discovery and actual Ethernet frames. This is stronger than the previous lab's native task-delivery claim. This document proposes the boundaries and proof gates for that target.

## 1. Three evidence levels

The existing five-VM lab sends task messages and route announcements in native Ethernet frames, but its node OS still supports IP for administration. It uses a fixed admitted roster, at most 16 members, four neighbors and seven task hops. Its evidence must retain that description.

The next **strict virtual node** has a kernel built without IPv4/TCP/IP or IPv6 support. It boots from local images, uses native Ethernet for inter-node messages, and uses a local Unix socket or in-process interface for its agent. Its serial/hypervisor console is outside the guest network. This proves an OS and protocol execution boundary, not manufacturing or performance on physical hardware.

The later **strict physical node** runs the reviewed image on an ordinary computer with supported Ethernet NICs. It boots from local storage and is administered by a local serial/USB console. Separate firmware, NIC management engines and any BMC must be audited or disabled before claiming that the whole physical device has no autonomous IP traffic. An IP-capable hypervisor or off-device operator console is disclosed; it is not an IP path inside the strict node.

No stage means that the public website, source downloads, build machines or the rest of the world stop using IP. No inter-site IP tunnel qualifies as a native physical link under this RFC.

## 2. Reuse the physical network, replace the network protocol

The first device design reuses Linux scheduling, storage, device drivers and Ethernet PHY/MAC hardware. It does not require custom silicon, an original OS or a new cable standard. An ordinary Ethernet switch can forward frames without serving as an IP router; the pilot must verify that its selected equipment passes the experimental frames and does not impose an unexpected gateway or controller dependency.

MAC addresses are link locators, not AgentIDs or proofs of ownership. A NIC replacement or a different permitted local MAC must not create a new logical agent. A switch's management IP, if any, is outside its forwarding function and outside a strict endpoint OS; an unmanaged, isolated switch or direct cables gives a clearer first test. Shared office Ethernet is not an acceptable first experimental segment.

Each native router receives a frame on one admitted link, applies the IPvX forwarding decision and emits a new Ethernet frame toward its next neighbor. Destination MAC changes at the native router; end-to-end AgentID does not. A Linux bridge joining every NIC would hide the routing question, so the router prototype must not bridge its interfaces or enable an IP forwarding path.

`0x88B5` remains a local experimental EtherType for the isolated pilot. It is not an assigned production IPvX identifier or an IANA protocol-number allocation. [Linux's Ethernet constants](https://github.com/torvalds/linux/blob/master/include/uapi/linux/if_ether.h) identify it as local experimental use. Production identification and coexistence require a separate standards decision.

## 3. Strict node OS profile

The proposed resolved kernel configuration requires `CONFIG_NET=y`, `CONFIG_PACKET=y` and `CONFIG_UNIX=y`, with `CONFIG_INET` and `CONFIG_IPV6` unset. The chosen NIC driver and offline boot/storage/console support must be built into the image or included as pinned local modules. Configuration assertions are checked after dependency resolution, not only in an input fragment.

[Linux network Kconfig](https://github.com/torvalds/linux/blob/master/net/Kconfig) separates Internet-protocol support from [packet sockets](https://github.com/torvalds/linux/blob/master/net/packet/Kconfig). [The kernel packet-socket documentation](https://docs.kernel.org/networking/packet_mmap.html) describes direct link access. These are the proposed implementation primitives; they do not by themselves implement IPvX identity, reliable delivery or secure routing.

Runtime probes must show that both stream and datagram creation for `AF_INET` and `AF_INET6` fail with the documented unsupported-family result. Positive probes must show that `AF_PACKET` and `AF_UNIX` work. The evidence bundle includes the exact kernel source revision, resolved configuration, image hashes, boot log, probes and complete captures of every experiment-facing link from before guest execution.

This removes the kernel Internet-protocol implementation; it is not a formal proof that arbitrary software cannot implement IP in user space through raw Ethernet. The reviewed image, daemon protocol, absence of a user-space IP helper and complete observed traffic are additional parts of the strict claim. Unused Internet-related routines in a general-purpose library must not be confused with a working IP delivery path, and an unreviewed new helper invalidates the image's acceptance until rechecked.

The strict image contains no network installer, DHCP client, DNS bootstrap, NTP dependency, SSH listener, HTTP inference server or package download at first boot. Loopback TCP is also unavailable. Agents use a Unix socket or directly linked model runtime. The strict task must fail visibly if a dependency tries to open an Internet socket; no host HTTP proxy or hidden inference gateway may make it succeed.

## 4. Boot and identity creation

1. The operator prepares a version-pinned image and, for a model experiment, exact local model weights on a separate build machine. All hashes, patches and licenses are recorded. This preparation may use the Internet and is not represented as a native transfer.
2. The device boots local storage. Its network daemon waits for a working cryptographic random source; it must not substitute a timestamp, MAC, shared image seed or a hard-coded private key.
3. On first initialization the endpoint generates its private identity keys locally, then persists them in a restricted state directory or suitable hardware-backed key facility. Public images contain no endpoint private key. A TPM is an optional storage mechanism whose integration still needs implementation and tests; it is not assumed to exist on every pilot machine.
4. The device displays or exports its public fingerprint through the local console. The operator can admit that fingerprint out of band. Restarting preserves the ID; deliberate reinitialization creates a new identity and is recorded.
5. The daemon discovers link neighbors and establishes only the permitted relationships. No public-domain lookup or central address-allocation request is part of this sequence.

The existing lab derives its textual agent identifier from a signing public key. A future NodeID/AgentID namespace and algorithm version must be specified with test vectors before claiming wire compatibility. A **NodeID** denotes a forwarding participant; an **AgentID** denotes an actor that may move, coexist with other agents or have several attachments. An attachment maps a permitted AgentID to a current node and local link. Random flat identifiers do not encode routes or automatically aggregate into a global forwarding table.

## 5. Native neighbor discovery and admission

The target authenticated bootstrap is a proposal, not an implemented feature of the current fixed-roster lab:

1. An interface emits a small, versioned native `HELLO` frame to link broadcast or a separately specified local discovery address. It carries no task payload, and routers do not forward it beyond that link.
2. The response supplies a fresh challenge. The peers bind protocol/version, role, public identity, both nonces, link context and relevant capabilities into an authenticated exchange. The exact transcript, canonical encoding and domain separation need reviewed vectors; a bare signed reusable announcement is not enough to prevent replay or bind a new session.
3. Each peer checks public-key/ID consistency and proof of key control. It independently applies its out-of-band admission pins or a specifically trusted scoped policy. Discovery is not permission to forward, membership is not physical reachability, and a valid signature is not proof of honesty.
4. Only after admission does the neighbor become eligible to exchange route announcements or tasks. Unknown nodes remain in a small, expiring, rate-limited pending set or are rejected. The operator can review them locally; the default is not open enrollment.

An attacker can generate many valid keys. This design does not solve Sybil attacks by hashing a key, using a blockchain label or asking an LLM. Neighbor caps, bounded pending state, frame-size checks, per-link/per-identity rate limits and explicit admission are required in the first authenticated test. Malformed or version-incompatible traffic must produce bounded, non-amplifying handling.

Freshness cannot silently depend on network time fetched over IP. Initial challenges use randomness and local monotonic deadlines. Persistent sequence floors or boot epochs need a crash/replay design. Expiring signed credentials require a documented trusted wall-clock source or must fail closed when that source is unavailable. A battery-backed clock, provisioned local time or signed native time service has distinct trust assumptions; none is assumed solved here.

## 6. Forwarding and transport responsibilities

Native links advertise admitted node reachability. The first topology is deliberately small. The proposal in RFC-0005 to separate access attachment from aggregate inter-router reachability remains research; this RFC does not promise global flat-ID routing.

Each data frame needs a reviewed version, message kind, bounded length, relevant source/destination identifiers, message/sequence association and hop bound. Parsers must use explicit byte order and reject inconsistent lengths, unknown critical fields, invalid authentication and exhausted hop budgets before allocating unbounded memory. End-to-end task encryption, hop/session authentication and receipt meanings must remain distinct.

Initial tests should use payloads below the declared Ethernet MTU. Larger messages require explicit bounded fragmentation, reassembly deadlines and quotas, authenticated association and loss handling. Retries, acknowledgments, backpressure, congestion control, fairness and durable application idempotency are not replaced by Ethernet or a checksum. TCP's absence creates these implementation responsibilities; it is not evidence of improved speed.

Dedicated routers may keep these costs away from model execution, as proposed in RFC-0005. No miner, mandatory global validator, blockchain finality or model inference is placed in the per-packet path. Scoped attestations are optional control-plane research with explicit outage costs.

## 7. Two prototype tracks that must not be confused

**Strict-OS smoke test:** a small C or Rust daemon can first demonstrate boot without Internet socket families, link discovery, deterministic task transfer and forwarding through a multi-NIC router. If it uses a test-only header such as `XNS1`, static node labels and a CRC, its report must say that authentication, encryption, secure discovery, production interoperability and real model work are absent. A CRC detects accidental corruption; it is not protection against a malicious sender. This isolated diagnostic is not a replacement for the authenticated lab protocol.

The parallel implementation contributor reported an intended stronger `XNS1` diagnostic: locally generated Ed25519 keys, NodeID derived from the public key, signed HELLO/task/result records and trust on first use on fixed isolated links. That direction can test key control after first contact, but it does not authenticate the first encounter against an independent trust anchor, establish project admission or preserve identity across a reboot without persistent storage. Static labels A/R/B would describe placement, not be the identity. This is an attributed work-in-progress description; a source revision and successful strict-guest run are still required before reporting it as implemented evidence.

**Authenticated native stack:** later replace diagnostic labels and checksums as trust mechanisms with the specified local identity, admission, authenticated neighbor sessions, task envelopes and reviewed delivery semantics. Porting or reusing the existing lab's code does not establish that it runs in the strict image until it actually passes the strict probes and dependency audit.

A minimal initramfs and compiled diagnostic daemon make the first proof inexpensive. A Python runtime may be carried offline for compatibility but must not be presumed to fit the small image or avoid Internet-socket dependencies. The subsequent LLM stage loads local weights and calls inference in process or through `AF_UNIX`; it reports model time separately from network time.

## 8. Virtual wires and physical prototype

The first executable virtual topology can be A–R–B: A and B each have one virtual NIC, R has two, and there is no A–B link. A four-guest diamond A–R1–B and A–R2–B adds a real alternate route; A and B then need two distinct interfaces. Three guests do not demonstrate route failover by themselves.

QEMU virtual Ethernet wires use direct Unix-domain stream connections between QEMU instances. [QEMU documents the Unix stream backend and packet-dump filter](https://www.qemu.org/docs/master/system/qemu-manpage.html). The selected command line and QEMU revision must be captured and checked for absence of an implicit default user-network NIC. A Unix socket connected to `passt` is excluded: it would introduce an IP-stack helper. TCP/UDP socket backends, SLIRP/user networking, IP tunnels and a host service carrying the task payload are excluded.

The virtual host may keep IP for its own administration. The claim is that strict guests and their virtual Ethernet wires do not use it. This is narrower than physical deployment and must be labelled accordingly.

For physical A–R–B, use two ordinary endpoint PCs with one supported Ethernet port each and one router PC with two supported ports. Connect A directly to R's first port and B to its second. The software and per-link capture must show the ingress/egress relationship. A later redundant physical topology needs the extra ports and cables or a separately documented switch/segment arrangement; a common switch alone must not provide a hidden direct A–B bypass. No purchase or modification of existing infrastructure is authorized by this draft.

## 9. Public research, private operations and discussion

The public research repository should contain the RFCs, reviewed reference source, schemas and vectors, strict-image recipes, synthetic fixtures, public safety limits and sanitized experiment evidence. Before a release, its exact revision and reproducibility state are recorded. A proposal or unexecuted recipe is not a successful experiment.

Private repositories remain appropriate for infrastructure inventory, operator access, deployment secrets and raw captures containing private material. They must not be the only location of the implementation needed to reproduce a claimed public result. Evidence is exported through an explicit allowlist, not by publishing a whole private directory. Contributor access to research source and access to running machines are separate decisions.

The seed discussion set is RFC-0001 identity/messages, RFC-0002 bounded routing, RFC-0003 participation, RFC-0004 evaluation, RFC-0005 role separation and this RFC-0006 strict boot. All are drafts. Comments propose changes against a named revision, supply reasons or reproducible counterexamples, and retain attributed responses. The append-only project history records proposals, reviews, adoption, implementation and measurement separately.

Maintainers moderate spam, abuse, secrets and unsafe executable submissions; a removed sensitive detail is recorded without repeating it. Substantive disagreement remains visible and is resolved through reviewed changes and the project's declared approval process. Human Relcom ID sign-in, blog authorship, a GitHub comment and model output do not automatically grant a vote, network admission or a private credential. No automatic execution of contributed models or code follows from a comment or majority label.

## 10. Proof gates and rejection rules

**G0 — Reproducible artifacts:** publish pinned source/toolchain/image/model hashes, resolved configuration and complete commands. A configuration fragment alone is insufficient.

**G1 — Whole guest OS:** all IPv4/IPv6 stream and datagram probes fail as specified; raw Ethernet and Unix-local probes pass after boot and restart. No management or inference TCP socket inside the guest is permitted.

**G2 — Link evidence:** capture every experiment-facing link from boot, without an EtherType filter that would conceal unwanted traffic. The report enumerates EtherTypes and decodes any VLAN nesting. IPv4 (`0x0800`), ARP (`0x0806`), IPv6 (`0x86DD`) or other unaccounted encapsulation on these links fails the strict native-only gate. Completeness of the capture and the frame parser must be tested; a packet count of zero is not proof of working delivery.

**G3 — Actual forwarding:** a unique task travels A–R–B, R's two interfaces show the expected same task association, B processes it, and A receives the corresponding result. Removing R or its link prevents delivery; direct A–B communication has no physical or virtual wire. The four-node extension must independently demonstrate failover and bounded convergence.

**G4 — Identity and trust:** for the authenticated track, identity persists across reboot/NIC replacement, ownership and admission are checked separately, unknown/forged/replayed traffic is rejected, key storage contains no image-shared private key, and memory/CPU/state bounds hold under hostile discovery. A diagnostic CRC-only track is explicitly not tested for G4.

**G5 — Agent task:** an offline local model performs a real collaborative task over the native path, with task inputs, actual outputs, correctness rubric, failure cases and latency/resource accounting. A deterministic echo or document function is a useful earlier test, but it cannot satisfy this model-work gate.

**G6 — Physical evidence:** actual supported equipment, image hashes, connection diagram, boot-console record and complete physical-link captures reproduce the relevant virtual gates. A QEMU result cannot satisfy G6.

**G7 — Useful comparison:** compare native and ordinary IP implementations using equal endpoint/router resources, security properties, hop counts, model versions, workload and impairment schedule. The strict and IP configurations are separate images. Report total bytes/CPU, convergence, completion/deadlines, sustained goodput, tail latency and failures. No advantage is claimed until measurements support it; global Internet performance and adoption remain outside the first physical pilot.

This RFC is ready for comments as an initial experiment specification. Acceptance, implementation and successful measurement require their own versioned records.

## 11. Measured appendix — first strict guests, 2026-10-27

The initial whole-guest transport test has now executed in [CI run 40500966557](https://github.com/relcom-technologies/ipvx-research/actions/runs/40500966557), source revision `90adf2c66cef042d0a663d0e34c097963f6b775d`. This appendix supplements the earlier proposal without accepting the RFC or marking its remaining gates complete. The initial work-in-progress descriptions above record the design before this run.

Three actual QEMU Linux 6.12.50 guests A–R–B ran on one CI host, connected through two direct Unix-backed Ethernet links. INET, IPv6 and loadable modules were compiled out. Each scenario recorded 12 `EAFNOSUPPORT` results: IPv4/IPv6 stream and datagram probes on all three guests. AF_PACKET and AF_UNIX were available. This was not merely a normal IP-enabled OS with its addresses removed.

In the baseline, B computed SHA-256 for 16 distinct 1,024-byte tasks and A checked 16 correct results. All 90 frames in the two complete link captures were verified; the observed EtherType was only `0x88B5`. The separate negative run stopped the only R after startup: zero of 16 tasks completed, with the expected timeout; all 10 captured frames were verified. This supports the absence of a hidden delivery bypass in the tested image and links. It does not demonstrate route repair: the next-hop table was fixed and there was no alternative path.

The XNS1 diagnostic used guest-generated Ed25519 keys, public-key-derived NodeIDs, signed HELLO/task/result frames and first-use bindings on the fixed links. Keys lived only in RAM. Origin signatures, CRCs and recipient associations were verified; mutable hop fields and the next-hop link are not fully authenticated by this diagnostic. It had no encryption, persistent identity or independently trusted admission. It is not a compatible version of the earlier encrypted mesh.

The local model and Unix-socket task interface in the diagram remain target work. AF_UNIX availability was probed, but no model or model-facing SDK task ran in these strict guests. The SHA-256 task is deterministic computation. Physical hardware, hostile admission, durable recovery, dynamic routing and an equal-budget IP efficiency comparison remain untested. The host/build Internet and operator trust remain disclosed.

Source/config/image hashes, receipts, full captures and console records are linked in the [public measured summary](https://ipvx.org/data/strict-native-2026-10-27/summary.json). This run supplies bounded evidence toward G1–G3. It does not complete G4–G7 or prove bit-for-bit reproducibility of every host package. A subsequent change needs its own frozen revision, evidence and decision.
