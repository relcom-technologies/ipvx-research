# Agent Card 0.1.1: disclosure and frozen-version boundary

This proposed descriptor patch discloses existing recovery limits in machine
readable discovery and the short guide. It does not change store code, token
lifetime, limits, request matching, decision revision or task/proposal storage.
There is no guaranteed minimum retention and no retention-expired tombstone.
A missing record is not evidence that a request was never accepted. Clients must
retain canonical params and the account/messageId binding; if recovery cannot
establish an outcome, keep UNKNOWN, stop automatic resubmission and reconcile
with the operator before choosing a replacement messageId. Token validity for
30 days is not a retention SLA.

## Preserve the original candidate

IPVX-A2A-INTEROP-001 1.0-rc1 remains pinned to service revision
`f56939c90fe4b1c508cee99678890b4281b6e7b7`. Its protocol, manifest, harness and
recorded local preflight bytes remain unchanged. Changing even a description
changes that source hash. The original preflight therefore correctly rejects
this working tree's new descriptor; bypassing its integrity check would be wrong.

The three source files named in the original protocol are preserved byte for byte
under `experiments/a2a-interop/frozen-source/f56939c90fe4b1c508cee99678890b4281b6e7b7/`.
They are an isolated test fixture, not the deployable service. CI verifies their
hashes and the original six bundle-file hashes, copies them to a temporary root
and runs the untouched A/B/R harness in a separate interpreter. The current
service has its own SDK, retry, privacy and discovery tests. A passing frozen
regression does not measure 0.1.1 as a new interoperability candidate.

No successor execution scope is approved here. Before any joint pilot, select
a reviewed service revision and harness, create a separately versioned successor,
recompute its scope hash, obtain explicit scope ACKs and a separate owner launch
decision. The original unaccepted window has elapsed. A public-text reviewer is
not an authorized independent client runner. No live exchange, model execution,
resource allocation or deployment is part of this change.
