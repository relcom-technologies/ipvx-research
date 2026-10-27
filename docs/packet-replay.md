# Saved full-capture replay and downloads

`packet-replay.html` visualizes all 90 baseline and 10 relay-removed frames from
strict run 40500966557, source `90adf2c66cef042d0a663d0e34c097963f6b775d`.
This is not a new run, live telemetry, LLM execution or multi-host strict OS proof.
The separate earlier LLM trace retained IP in its management operating systems.

`scripts/export_packet_replay.py` first checks the capture and console hashes
against the original receipts, then independently verifies every captured frame
using the public strict verifier. It preserves the frame number, exact timestamp,
whole frame bytes/hash, signed sender/destination IDs and payload. It never edits
the original captures or receipts. Browser text says the exporter verified the
signatures; no browser cryptographic verification is claimed.

## Clock and order limitation

The installed QEMU package was 8.2.2. Its dump filter uses each process's virtual
clock and a start offset ([upstream source](https://github.com/qemu/qemu/blob/v8.2.2/net/dump.c)).
The two captures have no established common clock. A direct timestamp sort placed
some forwarded task frames before the corresponding sending frames. Such a sort
does not establish chronology or hop latency and was rejected before publication.

The replay preserves each file's recorded order. For TASK and RESULT it additionally
matches immutable signed content across the relay (ignoring only relay-mutated
hop limit and CRC) and requires source before forwarded frame. A topological order
combines those constraints. All remaining inter-link ordering, including repeated
HELLO frames without a unique sequence, is illustrative. The display shows elapsed
time only from the first frame of that same PCAP. No global latency is calculated.
The replay interval is expressly an explanatory display speed.

Pause, next/back, native range input and all-row selection keep access independent
of animation. Reduced motion removes the moving dot. Switching scenario, resizing,
leaving the page or changing motion preferences stops playback. Invalid or missing
data disables playback and provides retry while original evidence remains linked.
The exact moment of relay termination is not a fabricated timeline event.

## Public bundles

`scripts/build_downloads.py` generates two deterministic, bounded ZIP files from
explicit public trees. The prototype includes code/config/instructions, evidence,
RFC-0006/0007 and the device guide. Compiled images, model weights, private lab
source, credentials and state are excluded. The source README retains the original
pre-run state; README-RU and the dated result explain the completed smoke run.

The history bundle includes every current canonical event and actor plus readable
and structured exports. Historical commit manifests keep their original snapshot
scope. A history event does not imply publication or ratification. `manifest.json`
records byte size, file count, SHA-256 and the last included history event.
`downloads.html`, RFC-0006, reproduction, history and portal footer expose downloads
without sign-in. Publication still requires the normal protected-main review and
exact-release deployment. Local preview availability is not public-domain success.

Rebuild with `build_downloads.py`, `export_packet_replay.py`, then `build_portal.py`.
Verify actual browser behavior with `browser_replay_check.mjs`; the normal browser
workflow also checks both HTTP downloads against their byte counts and hashes.
