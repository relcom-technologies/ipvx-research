# IPvXResearchLiaison

This service prepares technical replies from public discussion and versioned
project evidence. Claude writes a draft; GPT checks it. These are two backends of
the same project representative, not independent researchers. The local adapter
supports an explicitly configured Ollama server on loopback; no local inference
has been measured for this service yet.

The owner authorized **3 USD/day shared across providers**, measured by calendar
day in Europe/Berlin. SQLite reserves maximum output cost plus a margin before
generation, using provider input-token counts and the configured prices. Failed
or uncertain calls keep their reservations. Concurrent workers share the ledger;
there are at most eight generation calls/day. SDK retries are disabled. An expired
price record, absent credential or exhausted balance stops new generation.
Prices must be reviewed before `pricing_valid_until`; custom/region/priority
pricing is outside this default configuration. This ledger is not a provider
billing statement. No tools, browsing, model execution or resource grants are
exposed to a model.

Collection is independent of generation. `generation_enabled=false` keeps the
public mirror refreshed and leaves new questions unprocessed for later model
work. Only the reviewed release snapshot is baselined as historical. Budget
preflight defers a new question before allocating its job or calling a provider;
it is not marked as answered. Two successful model responses are required before
the operator enables scheduled generation. The timer can therefore keep reading
discussion while a provider prerequisite is being resolved.

## Credentials

The dedicated OpenAI/Anthropic keys are already installed privately under
`/etc/ipvx-liaison` on the existing server and passed through systemd
LoadCredential. GitHub Actions are not a credential transport or runtime.
Do not read their values into chat, copy an owner GitHub token, or replace keys
as part of a source update. Keys are excluded from public exports, logs and
model prompts. The root-owned configuration is passed as a separate credential. No API key belongs in this
repository. `billing_authorized` remains false in the checked-in example.

## Run one private draft

Install `requirements.txt` in a dedicated virtual environment. Copy the example
configuration to private state, enable billing only after deployment checks, and
inject the two named credentials. Then:

```sh
python services/liaison/agent.py --config /private/state/config.json \
  --snapshot data/community-discussions.json --facts services/liaison/facts.json \
  --state /private/state/ledger.sqlite --comment COMMENT_ID \
  --output /private/state/reply.json
```

The result records provider, requested and actual model, usage, reserved cost,
prompt/evidence hashes, source ID, coverage and editorial decision. It remains
`draft_only`, even when the reviewer accepts it. Publication must have its own
outbox/receipt; this module does not send social messages. A process crash after
reservation is an uncertain call, not permission to retry it automatically. Job
versions are unique and earlier project replies are not re-posted.

Both model input and output texts are preserved in private transcripts, including
invalid JSON output. These contain public discussion and the supplied project
context, not credential values or hidden reasoning. A manual smoke retry uses
`IPVX_LIAISON_RETRY_ID`, a distinct 32-character hex operator nonce; the original
failed job and its cost reservation remain intact. Scheduled polling does not
invent retry nonces or repeat uncertain provider calls automatically.

## Evidence and implementation boundaries

Public-source export: `scripts/export_community.py`. It excludes deleted, spam
and pending-verification messages and stores only whitelisted public fields.
Moltbook's returned tree is known to omit some deep replies; its counters and an
empty delta do not prove complete coverage. Private A2A submissions are not sent
to model providers or silently turned into public comments.

Official API references reviewed 29 October 2026:

- [OpenAI Python API](https://developers.openai.com/api/reference/python)
- [GPT-5.5 model and pricing](https://developers.openai.com/api/docs/models/gpt-5.5)
- [Claude Python API](https://platform.claude.com/docs/en/api/python)
- [Claude Sonnet 4.5 model](https://platform.claude.com/docs/en/models/sonnet-4-5/overview)

Focused tests cover concurrent budget reservations, the Berlin day boundary,
duplicate versions, untrusted model decisions, expired prices, attribution and
public-mirror isolation. Passing synthetic tests does not establish a successful
paid API call, live deployment or automatic publication.

## Autonomous analysis and proposals

The server reads only the three approved public threads: Moltbook Infrastructure,
A2A discussion 2406 and ClawMesh issue 1. GitHub discussion parsing is explicitly
limited to visible public HTML comment bodies; missing bodies or format drift
are missing coverage, never an empty complete discussion. Existing Moltbook
depth-five incompleteness remains. Private A2A applications remain outside model
inputs. Public replies, source coverage and versioned facts are untrusted input
data; models have no tools, publication credentials or execution authority.

Claude classifies and drafts; GPT reviews the same evidence and may reject or
replace the draft. Concrete experiment/review interest requires a structured
proposal: one hypothesis, roles, agreed/unagreed resources, versions, shared task,
control, failure cases, success/failure metrics, time/compute limits, artifacts,
owner decisions and consent status. Review-only is a valid role and must not be
turned into a runner commitment or repeated execution questions.

Private transcripts and validated drafts persist in the existing ledger/drafts
directory. A separate private notification feed omits prompts, raw source text,
keys and transcripts; it is intended for the existing owner-only mail notifier.
A committed SQLite draft is rematerialized after a file-write interruption.
The successful explicit smoke version is marked handled to avoid another paid
analysis of the same comment on the next timer tick. Historical failures and
reservations remain unchanged.

A current two-provider readiness receipt is mandatory before scheduled paid work.
A permanent provider/quota/auth failure blocks further automatic provider calls
until a successful explicitly authorized new smoke; old failure evidence is
archived, never erased. Exhausted daily budget defers unstarted versions, and
expired prices stop before job allocation or provider requests. A single process
lock prevents overlapping smoke/timer workers. No SDK retry is enabled.
