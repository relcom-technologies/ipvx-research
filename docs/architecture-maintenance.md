# Maintaining the network architecture

The architecture page depicts the measured strict-agent run, not a live
network. `scripts/research_architecture.py` obtains counts and the source
revision from `data/strict-agents-round.json`. Labels and stage descriptions
are manually curated in four languages. The physical scope, absence of INET
and IPv6 in guest kernels, IP-based external management, routing evidence and
unmeasured quantities must remain explicit. The playback timing is illustrative.

`data/architecture-evidence.json` records SHA-256 digests of the strict-agent,
native workload and scale-model summary files. The page build fails when a
listed file changes until a contributor has reviewed the architecture and
updated the digest. This checks known files only: when a new experiment is
published, its contributor must register the new source in the evidence list,
assess whether the diagram or claims need updating, and describe the changes and
limits in the attributed history. A hash verifies that the reviewed source has
not changed; it does not itself prove that every new experiment was discovered
or that a claim is true. Simulations must remain labeled as simulations.

For an update, review the public evidence and provenance, update the four
language dictionaries together, update the evidence list and its allowed set,
then run the normal site, history, localization and layout-browser checks.
