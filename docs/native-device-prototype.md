# Native-device prototype plan

Date: 2026-10-27. Status: **implementation plan with a measured first-run appendix below**. See [RFC-0006](../rfc/0006-native-devices-and-bootstrap.md) for the protocol/trust boundary. The earlier native lab measurements alone did not prove this stricter OS profile; the separate strict-guest run now supplies specific additional evidence.

## What the first run should prove

Boot a small Linux system that cannot create IPv4 or IPv6 sockets, then send a real Ethernet task across two separate links through a router. Keep the model task, authenticated identity and physical-machine stages explicit rather than making one small diagnostic carry all those claims.

The strict-native diagnostic work is separate from the existing encrypted mesh. At the time the initial plan was written, its kernel build, VM boot and packet delivery had not been established. The measured appendix records their subsequent execution; the remaining milestones retain their proposed status.

The current intended diagnostic revision adds OpenSSL Ed25519 signatures, a public-key-derived NodeID and TOFU on fixed links. This is stronger than the earlier CRC-only option, but neither TOFU nor a signature proves independent admission. The contributor has not claimed persistence across reboot, encryption, compatibility with the existing mesh or model inference. Its proposed workload is deterministic SHA-256 tasks rather than an LLM task. Report the actual frozen revision and observed behavior when available; do not fill these gates from the plan.

## First topology

```text
local task -> A [NIC a] == wire AR == [NIC ra] R [NIC rb] == wire RB == [NIC b] B
              guest       Unix FD      guest       Unix FD      guest
```

The two virtual Ethernet wires are direct QEMU-to-QEMU Unix streams, not TCP, an IP bridge service or a `passt` process. R does native application forwarding between its two NICs; it does not make a Linux bridge. A and B have no common link. A host process starts VMs and reads console/evidence files but must not relay their task payloads.

A later four-node diamond introduces R1 and R2, four independent wires and two NICs on each endpoint. Only that extension tests route choice and loss of one usable route. Preserve the simpler three-node run as a separate milestone.

## Build inputs and guest layout

Pin and record Linux source, toolchain, BusyBox or other init, cryptographic dependencies, daemon source and QEMU version. Keep build artifacts in an isolated task directory. A read-only initramfs contains `/init`, the diagnostic/probe executable, required shared libraries if any, and no network package manager. A local writable state device is needed before identity-persistence tests; a fresh immutable image without persistent state must not be advertised as preserving an agent identity.

Required resolved kernel settings:

```text
CONFIG_NET=y
CONFIG_PACKET=y
CONFIG_UNIX=y
# CONFIG_INET is not set
# CONFIG_IPV6 is not set
```

Also enable the selected architecture, local console, initramfs, device filesystem and actual virtual NIC driver; `CONFIG_VIRTIO_NET=y` is the candidate for a virtio-net image. Physical NIC drivers are a separate hardware-specific selection. Include the resolved configuration in the evidence; optionally enable the kernel configuration export so the running image can expose it locally. Run normal Kconfig dependency resolution and fail the build if it changes the required settings. These settings are supported by the [official Linux networking configuration](https://github.com/torvalds/linux/blob/master/net/Kconfig) and [packet configuration](https://github.com/torvalds/linux/blob/master/net/packet/Kconfig); they are not the entire machine configuration.

The guest init mounts required local filesystems, brings its known interface up using non-IP link control, then starts only the diagnostic and local task interface. It must not launch DHCP, DNS, SSH, NTP, an HTTP model server or an external model proxy. The future SDK uses a filesystem Unix socket with local access permissions or an in-process call. Fail explicitly on unexpected Internet-socket attempts.

The no-INET kernel is necessary evidence, not sufficient evidence for the whole run: raw sockets could also carry a user-space TCP/IP implementation. Audit the selected image for such helpers and verify full traffic on every link. The result applies to the pinned image and observed experiment, not all possible programs that could later be installed.

## Verified QEMU building blocks

The [official QEMU invocation documentation](https://www.qemu.org/docs/master/system/qemu-manpage.html) supports Unix-domain stream backends. The following are **option fragments**, not a complete tested launcher. The launcher must supply pinned kernel/image/console arguments and validate the selected QEMU version:

```text
# First peer of one isolated wire:
-netdev stream,id=ar,server=on,addr.type=unix,addr.path=/task/run/ar.sock
-device virtio-net-pci,netdev=ar,mac=52:54:00:00:01:01

# Other peer, in a different guest process:
-netdev stream,id=ar,server=off,addr.type=unix,addr.path=/task/run/ar.sock,reconnect-ms=500
-device virtio-net-pci,netdev=ar,mac=52:54:00:00:01:02

# Per-link capture on the selected netdev:
-object filter-dump,id=cap-ar,netdev=ar,file=/task/evidence/ar.pcap,maxlen=65535
```

Each link has its own path and each interface has a distinct locally assigned lab MAC. Start listeners before connecting peers. Disable the implicit default NIC/user backend and inspect the effective device graph. Do not combine a claim of native-only wires with `-netdev user`, `passt`, INET socket backends, UDP multicast or IP tunneling. The kernel's serial console and a local QEMU monitor can be used without adding a guest network interface. No exposed host management listener is required for this run.

Unix stream support here transports emulated Ethernet frames; it is not evidence that the physical wire has been built. Record the command line and QEMU's effective network graph so an accidentally added default NIC cannot be hidden.

## Executable milestones

**M1: kernel and runtime probes.** Build and boot one guest. A compiled probe attempts IPv4 and IPv6 stream/datagram sockets and records return codes; all four must report the unsupported family. It also opens `AF_PACKET` and creates a local `AF_UNIX` exchange. Record image hash, boot log, config assertion and probe results. Repeat after restart. Absence of an IP address alone is insufficient: a normal IP-capable kernel without an assigned address fails this milestone.

**M2: three strict guests and two wires.** Boot A, R and B, capturing both links before guest code runs. Deliver a deterministic task and result. Record the task identifier at ingress/egress, TTL/hop behavior and output. Terminate R and verify that A cannot reach B. A task injected or answered through a host service invalidates the test.

**M3: protocol-negative cases.** Feed truncated frames, inconsistent lengths, oversized payloads, wrong version, unknown type, exhausted hop bounds, duplicates and bad checksums. Check bounded handling and correct error reporting. A checksum-only test makes no cryptographic claim. Publish which cases remain unsupported.

**M4: authenticated bootstrap.** Add locally generated persistent keys, reviewed challenge/response, admission pins, replay protection and bounded neighbor state. Test unknown and forged peers, boot/restart replay, key persistence, copied-image behavior and flood limits. This stage is not satisfied by static IDs, MAC addresses or a CRC.

**M5: actual agent work.** Carry a local model runtime and exact weights offline. Connect it by `AF_UNIX` or in process. Run a collaborative task with actual saved outputs and a correctness rubric; retain wrong answers. Include model/queue time separately from native network time. Then compare to a separate IP-enabled image under the same conditions.

**M6: alternative route.** Boot the four-node diamond and implement actual distributed route announcements. Measure primary loss, recovery, loops, stale state and convergence. Hard-coded alternate forwarding or a host controller selecting the route must be identified and cannot be called decentralized failover.

**M7: physical port.** Use supported ordinary hardware and two direct Ethernet links for the initial A–R–B reproduction. Inventory firmware/management features, disable autonomous network boot/remote network functions where appropriate, and capture the actual physical interfaces from boot. Validate NIC MTU, offload behavior, frame padding and capture/FCS assumptions. Do not purchase hardware or repurpose existing shared interfaces as a side effect of writing this plan.

## Evidence bundle and acceptance script

The eventual runner should produce a machine-readable result distinguishing `proposed`, `built`, `booted`, `passed`, `failed` and `not_tested`, together with:

- Source and toolchain pins, resolved `.config`, image hashes and startup commands.
- Guest console logs and positive/negative socket probes for each guest.
- Complete per-link PCAP from boot, with no protocol capture filter; parser version and EtherType totals, including VLAN-inner types where present.
- Task inputs, outputs and unique identifiers; observed ingress/egress associations, retries and failure attempts.
- Explicit authenticity/encryption/model/physical-hardware flags. Unsupported features remain false rather than inferred from delivery.
- Resource limits, elapsed time and missing evidence. No packet-rate, global-scale or adoption conclusion follows from a small smoke test.

Fail strict acceptance if any required config setting differs, a forbidden socket succeeds, boot/link capture is missing or incomplete, an IP/ARP/IPv6 frame appears, an unaccounted tunnel hides the delivery, or expected task delivery is absent. A zero-frame capture cannot pass. For authenticated/LLM/physical stages, fail or mark `not_tested` when their specific evidence is absent; never promote a weaker milestone to a stronger claim.

Keep local private keys, private deployment inventory and unreviewed raw data outside the public bundle. Publicly release the reviewed reference code/build recipes and enough sanitized evidence for independent reproduction. The public portal and moderation/governance workflow remain outside the strict native node and may continue using ordinary Internet services.

## Measured appendix — first execution on 2026-10-27

[CI run 40500966557](https://github.com/relcom-technologies/ipvx-research/actions/runs/40500966557) executed source `90adf2c66cef042d0a663d0e34c097963f6b775d`, including the public `experiments/strict-native` prototype. It built Linux 6.12.50, a static PID 1 with OpenSSL Ed25519, and an initramfs. Three whole guests ran on one CI host with two Unix-backed virtual Ethernet links. They did not use a management IP inside the guest.

The baseline receipt records 12 failed IPv4/IPv6 stream/datagram socket probes across three guests, successful packet/Unix support, 16 of 16 verified SHA-256 tasks of 1 KiB, and 90 audited frames, all EtherType `0x88B5`. The relay-removed receipt records the same 12 socket rejections, zero completed tasks of 16, expected timeout and 10 audited native frames. Downloaded captures and signatures were reverified locally by the project operator; this is not an outside audit.

The result establishes a first strict-OS transport execution toward M1/M2. Some bounded diagnostic checks ran, but M3's full hostile-input/resource suite is not complete. M4 is only partial: the guests generate and prove Ed25519 key control using fixed-link TOFU, but keys are volatile and admission is not independently anchored. M5 local LLM, M6 route failover, M7 physical hardware and the IP comparison remain unexecuted. No speed advantage is inferred.

The baseline kernel-image SHA-256 is `ded680a0afe613c2d18e77ef1f1a410a0da7818c098f1df615bdebcf5368f982`; initramfs SHA-256 is `f9d55b457359c9ceb8c4a61f6d38543fba201dc0899a7fcaf1aa7c5dfce89f6a`. Kernel archive SHA-256 remains the source pin recorded in the public summary. Tool/package versions are recorded, but not all host packages use immutable snapshots; do not claim identical rebuild bytes on any host.

See [public summary and evidence](https://ipvx.org/data/strict-native-2026-10-27/summary.json), [baseline receipt](https://ipvx.org/data/strict-native-2026-10-27/baseline/receipt.json) and [relay-removed receipt](https://ipvx.org/data/strict-native-2026-10-27/relay-down/receipt.json). This dated appendix preserves the original plan and updates the evidence state; it does not ratify the RFC.
