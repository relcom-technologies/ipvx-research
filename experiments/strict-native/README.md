# Whole-device native transport prototype

This is a separate **XNS1 experimental smoke-test**, not the existing encrypted
IPvX mesh protocol. It is source prepared for a real whole-kernel test. Until a
successful run produces verified receipts, no whole-guest result is established.

Three actual Linux guests are connected only by two virtual Ethernet links:

```text
Agent A -- Unix-backed virtual Ethernet -- R -- Unix-backed virtual Ethernet -- Agent B
```

The guests run a pinned Linux 6.12.50 kernel with `CONFIG_INET=n`, `CONFIG_IPV6=n`
and `CONFIG_MODULES=n`. They have no distribution, shell, package manager, DNS
resolver, DHCP client, TCP/UDP server or model inference service. A static C
executable is PID 1 and owns its packet sockets. Kernel networking and virtio NIC
drivers remain; this is removal of Internet protocol support, not a rewritten OS
or network card. Other kernel core facilities, including Unix sockets, remain.

Each guest generates an Ed25519 key in its own RAM. Its NodeID is SHA-256 of the
raw public key. Signed HELLO frames establish first-seen bindings between the
three fixed fixture roles and their keys. This **TOFU** binding proves possession
of the corresponding key, not permission, operator independence or a trusted
real-world identity. Keys are not persisted and a reboot produces a new ID.

Agent A sends sixteen distinct 1,024-byte blocks. B actually calculates SHA-256
of the received bytes and returns signed digests. A independently checks each
result. One duplicate task exercises B's bounded in-memory result cache; this is
not durable exactly-once execution. R verifies origin signatures and forwards
between its two interfaces using a fixed role-to-interface table. The static role
is a fixture placement label, distinct from the generated cryptographic NodeID.
This version does not implement dynamic route discovery or route repair.

The second run removes the only relay after all interfaces are ready. Expected
timeouts demonstrate the physical absence of a direct A/B path. This topology
cannot demonstrate failover; that needs a second relay/path in a later stage.

## What is checked

1. The final built kernel config contains the required packet, Unix and NIC support
   and lacks IPv4, IPv6 and loadable modules.
2. All three booted kernels reject both stream and datagram `AF_INET`/`AF_INET6`
   socket creation with `EAFNOSUPPORT`. Unix socket creation and every required
   packet socket succeed. A permission error is not accepted as absence of IP.
3. Full captures start with each QEMU Ethernet backend, without a capture filter.
   The verifier audits every captured EtherType, including VLAN inner types; an
   IPv4, IPv6, ARP or any other unexpected type fails the run.
4. Every captured XNS1 frame is bounded, has a correct CRC, a self-certifying source
   ID and a valid Ed25519 signature. Task/result recipient IDs match the actual
   booted peer keys. Both links must contain every completed task and result.
5. Sixteen independent SHA-256 reference results match, and the deliberate
   duplicate is observed. In the relay-removed case, actual timeout must prevent
   completion. No path failover, LLM task or speed advantage is inferred.

## Run on x86_64 Linux

The host needs GCC/glibc development files, Linux build tools, OpenSSL development
files including static libcrypto, QEMU and Python. On Ubuntu 24.04:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends -y build-essential bc bison flex libelf-dev libssl-dev qemu-system-x86 curl xz-utils gzip python3-venv
python3 -m venv .venv
.venv/bin/pip install cryptography==50.0.2
bash scripts/build.sh
.venv/bin/python scripts/run.py
```

After the tools are installed, build/run need no host root privileges, TAP,
network namespaces, firewall changes or physical interface configuration. The
initial download and CI/host management use the ordinary host Internet. Guest
Ethernet frames travel directly between QEMU processes through two `AF_UNIX`
stream sockets; `user`, `passt`, TAP, TCP and UDP backends are absent. QEMU's
default NIC is explicitly disabled. This says nothing about the host's own IP
stack or its unrelated traffic.

The kernel source archive is pinned by its official SHA-256:

```text
linux-6.12.50.tar.xz
c435bd74d1c21fc5a950781a50d78bae2b93944144694843359948ad3afc72a5
```

The compiler, OpenSSL and QEMU are Ubuntu packages; their actual versions are
recorded. They are not all locked to immutable package snapshots, so the recipe
does not claim bit-for-bit reproducibility. The guest is statically linked and
`readelf` rejects a dynamic ELF interpreter. Virtio RNG supplies entropy from the
host's random device; no private key is printed or exported.

`.github/workflows/strict-native.yml` is an example manual-only workflow assuming
this directory is the repository root. When included as a subdirectory of another
repository, update its working directory and artifact paths before dispatch. The
workflow has read-only repository permissions and no infrastructure credentials.

## Wire layout

EtherType `0x88B5` is used only in this isolated experiment. The 188-byte XNS1
header uses big-endian integers:

```text
0..3 magic XNS1 | 4 version | 5 TASK/RESULT/HELLO | 6 hop limit | 7 zero
8..11 sequence | 12..15 source role | 16..19 destination role
20..21 payload length | 22..23 zero | 24..27 CRC32
28..59 source NodeID | 60..91 destination NodeID
92..123 raw Ed25519 public key | 124..187 Ed25519 signature
188.. payload, at most 1300 bytes
```

CRC covers the header and payload with its own field zeroed; it detects accidental
corruption and is not authentication. The Ed25519 input is the same header and
payload with hop limit, CRC and signature fields zeroed. The relay can decrement
the hop limit without changing the origin signature. This prototype does not
authenticate mutable hop fields or each next-hop link. MAC addresses identify the
local Ethernet peer, not global identity. Signed HELLO uses an all-zero destination
NodeID. There is no fragmentation or confidentiality. Do not attach this prototype
to an untrusted/shared physical LAN.

## Evidence and current status

`build/artifacts/` contains the actual kernel, kernel config, static executable,
initramfs, source/build hashes and package/OpenSSL versions. Each scenario under
`build/results/` contains full pcaps, boot/console logs, QEMU error logs, exact
launch arguments and a machine-verifiable `receipt.json`. A failed build/run has
no passing receipt; its artifacts are still retained by CI.

On the author's macOS host, five synthetic parser/signature tests, the portable C
wire/CRC self-test and Python/shell syntax checks passed. The portable C test does
not compile OpenSSL guest mode, boot Linux,
verify kernel absence of IP or measure real virtual Ethernet delivery. Those
remain unrun until the Linux CI workflow executes. Even a passing Linux run would
be three software devices on one host and one operator, with deterministic tasks
and no LLM. External adoption, Internet-scale routing, persistent identity and
usefulness to independent agents remain separate hypotheses.

Primary references:

- [Linux source and checksum listing](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc)
- [Linux packet socket interface](https://docs.kernel.org/networking/packet_mmap.html)
- [Linux initramfs creation](https://docs.kernel.org/admin-guide/initrd.html)
- [QEMU Unix stream network backend](https://www.qemu.org/docs/master/system/invocation.html)
- [OpenSSL Ed25519 EVP interface](https://docs.openssl.org/3.0/man7/EVP_PKEY-ED25519/)
