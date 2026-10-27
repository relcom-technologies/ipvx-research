# RFC-0004 — Reproducible model and network evaluation

Status: Draft · not an IETF RFC.

## Separate questions
Can independent model processes collaborate? Does the selected transport deliver the messages? Is the final answer correct? Does it improve on ordinary IP? A pass on one question is not a pass on the others.

## Matched comparison
Freeze model weights and hashes, runtime, prompt, seed, evidence, token limit and hardware. Run native Ethernet A–R1–B, ordinary IPv4/TCP directly A–B, and matched-topology IPv4/TCP A–R1–B. Keep the same application identity, encryption and receipts. Alternate the order. Exclude declared warm-up. Measure fresh inference on every trial; do not report replayed answers as a new model run.

## Collaborative task
A drafts a research assessment using measurements; B critiques it using separately preloaded limitations; A synthesizes the final decision. Messages carry task IDs and structured text, not websites. Queue acknowledgement is immediate; model inference runs asynchronously. The coordinator only starts and observes the experiment.

## Report
Publish model outputs including errors, prompts and hashes, signed delivery traces, frame captures filtered to the experiment, per-call token and inference time, task makespan and fixed-payload network RTT. State sample size, hop count, operator count and whether any infrastructure underlay still uses IP.

## Current local model boundary
Qwen3-0.6B Q8_0 is an actual open language model chosen to fit existing CPU VMs. A result with this small model does not establish behavior of frontier models, independent organizations or the public Internet. Larger and researcher-supplied models need new approved experiments, not extrapolation.
