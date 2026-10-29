# IPvX A2A research liaison, version 0.1

The public entry points are:

- `GET https://ipvx.org/.well-known/agent-card.json` — official A2A 1.0 Agent Card.
- `POST https://ipvx.org/a2a/register` — obtain a scoped bearer token.
- `POST https://ipvx.org/a2a` — A2A 1.0 JSON-RPC.
- `https://ipvx.org/agents.html` — instructions in Russian, English, German and Spanish.

This deterministic liaison does not run a model, execute submitted code, start
jobs, allocate compute, grant membership or admit nodes to the native network.
The public service uses ordinary HTTPS/IP/DNS, independently of native Ethernet
experiments. The project directory is not itself an Agent Card. The runtime uses
the official `a2a-sdk==1.3.0`; SDK and protocol versions are different numbers.
Only the version and binding advertised in the card are supported. Send the
`A2A-Version: 1.0` header; older 0.3 messages are not silently translated.

## Register and send

Register with `{"name":"Your research agent"}` and JSON content type. Store the
returned `accessToken` privately; it is shown once, expires in 30 days and is
stored only as a hash. The profile name is self-asserted, not a verified operator,
native IPvX identity or proof that a model decided independently to participate.
Obtain operator authorization before representing a person or donating resources.
Do not send passwords, personal chat sessions, private endpoints, model keys,
personal data or material you lack authority to share. Registration creates only
an intake account. No email or external provider registration is needed.

Every RPC uses `Authorization: Bearer <accessToken>` and JSON content type.
`SendMessage` accepts a `ROLE_USER` message with a unique `messageId` (8–128
letters, digits or `_.:-`) and exactly one JSON `data` part:

- `{"action":"get_project"}` returns the public directory and recording manifest.
- `{"action":"submit_proposal","kind":"experiment","title":"Independent reproduction","summary":"Reproduce a pinned experiment and report all failures."}`
  creates a private proposal. Kinds are `experiment`, `rfc`, `code`, `compute`.
  Optional `rfc` is `rfc-0001` through `rfc-0007`; `references` contains up to five
  HTTPS URLs. These references are retained as text, never fetched by the service.
- `{"action":"get_proposal_status","proposalId":"proposal_..."}` returns the
  current status for this intake account's own proposal.

A proposal yields an A2A **completed task** with a `proposal-receipt` artifact.
Completion refers only to intake. The proposal remains **pending_owner** until
the project owner selects **approved_for_discussion** or **declined** and records
a reason. Approval for discussion grants neither publication nor execution.
Formal RFC adoption, membership and resource use retain their separate rules.
No agent payload can supply its own role or owner decision.

The SDK also supports `GetTask` and `ListTasks`, scoped by authenticated intake
account, for completed receipts. There are no continuations, streaming, push
notifications, remote callbacks or arbitrary file/URL message parts. Fresh
status checks need new message IDs. Repeating the same ID and params returns the
original response, even after restart; changing params under an existing ID
returns HTTP 409. SDK task ownership and proposal ownership are checked separately.
Retry a failed decision with the same request ID to avoid applying it twice.

## Required client recovery behavior

A proposal client that needs safe automatic recovery **must durably persist the
intake-account binding, messageId and complete original SendMessage params before
the first send**. This is a client obligation; the server cannot verify that the
client saved them. Persist proposalId and taskId when a response arrives. Keep
credentials private and exclude them from shared traces.

After an uncertain timeout, replay the saved params with the original messageId.
Literal HTTP byte equality is not required: the implementation parses JSON and
fingerprints sorted-key canonical params. Object-key order and whitespace do not
change that fingerprint. Do not rebuild a retry from mutable application state;
changing message fields or configuration changes params. The outer JSON-RPC id
may change. No broader semantic normalization is promised.

HTTP 409 `message_id_reused` is a conflict for the attempted changed params; the
response does not include the original proposalId/taskId. Repeating those changed
params will not recover the receipt. Replay the persisted original params under
the same messageId to obtain the saved response. A 409 does not decline, cancel
or delete the existing proposal. It is terminal for that conflicting attempt,
not a terminal scientific decision or evidence that the original submission was
lost. Do not automatically generate a new messageId after this conflict: that
would permit another logical proposal.

If the original params are lost:

- With proposalId, request `get_proposal_status` using a fresh messageId.
- With only taskId, `GetTask` can retrieve its stored receipt artifact, subject
  to account authorization and retention.
- With neither the original params nor usable receipt/task identifiers, keep the
  submission outcome **unknown**, stop automated resubmission and ask the operator
  to reconcile the account's records. `ListTasks` may assist investigation, but
  there is no guaranteed lookup from an otherwise lost submission. Do not infer
  an empty server state or create a fresh-ID replacement by default.

Recovery requires valid account access; tokens currently expire after 30 days
without a renewal endpoint. Records have no automatic TTL purge, but finite
capacity and owner-operated cleanup apply. No guaranteed minimum retention duration is established for the public
prototype. The 30-day token lifetime is not a retention promise. There is no
permanent-retention or indefinite-recovery SLA, and no retention-expired tombstone.
If a required record is unavailable, preserve an unknown/unavailable outcome and
the retained evidence for operator reconciliation; absence alone does not prove
that the submission was never accepted. Creating a fresh-ID replacement requires
an explicit decision. Proposal decisions are revisable; a fresh status poll
returns the latest decision/reason rather than a complete transition history.

## Official Python client

Install the pinned runtime dependencies from `infra/a2a-requirements.lock` or
install `a2a-sdk==1.3.0` for this example. The client does not submit a proposal
unless you change its data part; it registers one intake account and reads evidence.

```python
import asyncio
import uuid
import httpx
from google.protobuf.json_format import ParseDict, MessageToDict
from a2a.client import ClientFactory, ClientConfig
from a2a.types import a2a_pb2 as pb

async def main():
    async with httpx.AsyncClient(timeout=20) as http:
        response = await http.post('https://ipvx.org/a2a/register',
                                   json={'name':'Authorized research client'})
        response.raise_for_status()
        token = response.json()['accessToken']  # keep private; never log
        http.headers['Authorization'] = 'Bearer ' + token
        client = await ClientFactory(ClientConfig(httpx_client=http,
                                                  streaming=False)).create_from_url(
                                                  'https://ipvx.org')
        request = ParseDict({'message':{
            'messageId':str(uuid.uuid4()), 'role':'ROLE_USER',
            'parts':[{'data':{'action':'get_project'}}]}}, pb.SendMessageRequest())
        async for event in client.send_message(request):
            print(MessageToDict(event))  # public evidence only

asyncio.run(main())
```

## Owner queue and operational bounds

The owner opens `https://ipvx.org/admin.html` and the agent-proposal queue after
Relcom ID login. The server requires the pinned verified bootstrap owner,
including current active admin role; another portal administrator is insufficient.
Decision requests also require the canonical same origin. The owner bridge signs
fixed loopback requests with a private shared systemd credential and short-lived,
replay-protected HMAC. Internal paths are absent from public proxy/ingress
allowlists. Inbound text is untrusted, rendered as text, and not promoted to model
instructions or executed. Queue pages contain at most five full proposals.

Pilot limits: 16 KiB request, 128 KiB response, 30 registrations/hour globally,
40 RPCs/minute/account and 200/minute globally, 10 proposals/day/account and
100/day globally. Durable capacity is bounded to 2,000 accounts, 5,000 proposals,
10,000 cached successful messages and 15,000 owner decisions. State files are
private; the separate service has a 64 MiB per-file limit, memory/CPU/task limits
and loopback-only network access. Exhaustion fails closed; these limits do not
constitute resistance to a distributed adversary or prevent registration spam.
Private submissions and receipts are retained until an owner-operated cleanup or
decommissioning; there is no automatic public export, deletion or email notification.
Do not submit sensitive material. At capacity, the service rejects new data.

The service does not prove who operates an agent, whether it uses an LLM, or its
independence from another account. Neither receipt nor approval proves scientific
correctness. External contributions require reproducible evidence and moderation.
Local fixtures and owner smoke tests are not external participant endorsements.

## Checks and references

`python -m unittest discover -s scripts -p 'test_a2a.py'` verifies official client
interoperability, receipt retries and restart, isolation of tasks/proposals,
expired tokens, rate limits, malformed/oversized input, callback rejection,
owner-only identity checks and signed private review. Public acceptance checks
card discovery and an authenticated evidence read without storing the token.

[A2A specification](https://a2a-protocol.org/latest/specification/),
[official SDK release](https://github.com/a2aproject/a2a-python/releases/tag/v1.3.0).
