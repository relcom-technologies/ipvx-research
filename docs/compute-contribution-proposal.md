# Proposal: research compute contributions

Status: proposal. There is no open compute pool, automated enrollment, external
endpoint admission, job scheduler or public credential collection today.

A participant may offer CPU/GPU time, a machine under their own control, a
local model, a bounded allowance for an official API, or a supported chat-based
contribution where both the service terms and account owner permit the research.
A public proposal describes the task, resource class, available time, model and
license, region, expected limits, cost responsibility and ability to stop;
it contains no secrets, private endpoints, personal data or sensitive logs.

A future controlled trial would require separate approval, an agreed workload,
software/model versions and reproducible outputs; isolation from production and
other tenants; a least-privilege short-lived credential or contributor-run
worker; explicit limits on duration, spend, storage and network access; a
revocation mechanism; privacy and retention terms; a health and incident plan;
and public reporting of permitted metrics and negative results. Participants
must not hand over passwords or personal chat sessions; access to official APIs
or a contributor-operated process is preferable where permitted. No web form in
this proposal transfers credentials or grants access, and majority approval for
project changes is distinct from authorization to use a resource.

Questions to resolve with contributors: model service terms, legal basis and
retention, local execution isolation, cost metering, scheduling fairness,
reproducibility across hardware, abuse handling, and offboarding. The proposed
pool and any ability to execute jobs remain hypotheses to design and test.
