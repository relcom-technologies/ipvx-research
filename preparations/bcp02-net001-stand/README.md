# BCP 0.2 disposable stand preparation

**Resource request submitted; target preflight NOT_RUN. This is not a launch permit.**

The owner selected a new Proxmox VM and then instructed the assistant to request
resources through a PR. [Infrastructure PR845](https://github.com/relcom-technologies/relcom-infra/pull/845)
requests one disposable Linux x86_64 guest: **2 vCPU, 2048 MiB RAM, at most 10 GiB
of guest disk**, no autostart/public NIC and authenticated out-of-band management.
It does not create a VM. Node, VMID, capacity and private access remain pending.
The request deliberately skips legacy infrastructure CI, which can access live
Terraform. No production workflow, live plan or apply is part of preparation.

## Frozen inputs and status

- Accepted PR47 merge: `6ab9926a210f4600cb0d87fd709793e83a5e7e34`.
- Original runner source scope:
  `4e9f8d89ec0f2bf0ef646659356bdac15e94fca41f403be0460eaeeedd35171d`.
- `scope.json`: a separate preparation scope and its canonical SHA-256, including
  resource bounds and explicit exclusions. It is **not** the signed runner scope
  or an owner ACK. Never substitute one hash for the other.
- `artifacts.json`: downloaded immutable Debian image, publisher metadata, Node
  Linux archive/ELF, four Linux Python wheels and a Git archive, with exact hashes.
  Artifact bytes stay in private local storage; no Linux binary/image was executed.
- `preflight.json`: actual local preparation observations and pending target gates.
  Offline checks cannot stand in for kernel, clock, isolation or network evidence.
- `checks.json`: repeatable offline checks and preservation results. Prior history,
  accepted BCP source/evidence and the separate mesh stay unchanged.

Publisher metadata identifies Debian 13 build `20261026-2643`, Python 3.13.5,
cloud kernel package 6.12.113-1, iproute2 6.15.0-1 and libseccomp2 2.6.0-2.
These are **image contents**, not measured installed binaries. Hash the actual
Python, ip, Node, libseccomp, kernel config and any extra guest package after
provisioning. The image does not list qemu-guest-agent or Python venv packages;
arrange serial management or separately pin required packages before isolation.
Do not run a floating apt upgrade and retain the old image-content claim.

The downloaded image matches the immutable official release's SHA-512 checksum;
Node matches its official SHA-256. This is HTTPS publisher/checksum provenance,
not an OpenPGP authentication claim. The first image fetch saved a redirect HTML
response; the mismatch was caught before use, retained privately, and corrected
with HTTPS-only redirect following. It never became an accepted image pin.

## Handoff and allowed preflight

The infrastructure request requires a fresh, create-only allocation proposal and
private operator receipt before the guest exists. Never disable egress, install
software, change UIDs or create namespaces on an existing production machine as a
substitute. No credentials, private addresses, machine IDs or SSH connection
identifiers belong in this public preparation directory.

After allocation, confirm the new guest identity and inventory against the
operator receipt. Provision pinned dependencies and a trusted synchronized clock
before closing that guest's egress. Capture the final kernel/config/binary hashes
and immutable source checks. All non-loopback guest links must be DOWN and both
IPv4/IPv6 default routes absent; no default route alone does not block LAN access.
Use only the authenticated serial/guest-agent path after disconnection. Keep
private evidence directories 0700 and files 0600 and UIDs 60001–60004 unused.

The accepted `runners.bcp02.admission.preflight(config)` is a read-only environment
check and may then be invoked against an **external unsigned preparation config**
containing the actual guest identity and measured pins. It does not consume a
permit or start the controller. Leave `owner_launch_decision`, `owner_scope_ack`,
`accepted_window` and `owner_public_key` unset in this preparation. Do not edit the
accepted `runners/bcp02/launch-config.json`, issue a signed `launch:true` permit,
call `claim_once`, start `Controller`, invoke the CLI `run`, create the experiment
namespaces, bring up links, or send HELLO/DATA under the present authorization.
A future launch must repeat freshness-sensitive preflight; a preparation report
cannot remain current indefinitely.

No Linux target is available yet, so none of these target checks passed here.
The local Mac, a package download, and a green mocked unit test are not that VM.

## Gates still open before a launch request

1. Allocate the exact guest through the approved non-Actions infrastructure path;
   record capacity, create-only plan, identity, console route and actual limits.
2. Record the installed kernel/config/runtime pins and successful environment
   preflight on that guest, including real clock state and closed egress.
3. Resolve the dataset/admission lifecycle in a reviewed client change: the current
   controller exports a fresh dataset inside `run_all`, after consuming the permit.
   A current source/image permit therefore does **not** independently bind a
   pre-approved dataset hash. Do not call that a pre-frozen run dataset. Any staged
   dataset must also satisfy the protocol's 1800-second freshness bound; never
   relabel an expired dataset's time under its old hash.
4. Review a final launch candidate binding the actual source, host, runtime,
   dataset/freshness, evidence contract and accepted window, then obtain the
   owner's scope ACK and separate single-run launch decision. No key, ACK,
   execution window or launch authority is manufactured by this request.

The intended later experiment remains `fixture-state-ethernet`: A–R–B namespaces
and two veth links in one guest, no live EL/CL/RPC, chain transaction, model/GPU
call or production deployment. It cannot prove physical Ethernet, live Ethereum
finality, an IP-free whole device, independent operators or superiority over IP.
Existing mesh results and their negative evidence remain a separate experiment.
