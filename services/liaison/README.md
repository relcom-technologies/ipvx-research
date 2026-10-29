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

## Credentials

The owner's dedicated GitHub Actions secrets in `relcom-infra` are
`IPVX_OPENAI_API_KEY` and `IPVX_ANTHROPIC_API_KEY`. They must be injected only by
the scoped trusted deployment job, stored in a private service environment and
excluded from public exports, logs and model prompts. No API key belongs in this
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
