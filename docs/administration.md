# Portal administration

`admin.html` is a public HTML shell. All inventory, moderation and audit data come
from the private loopback community service after a verified Relcom ID session and
an effective `admin` role. Hiding a button is never an authorization boundary.

The owner requested management of users and access on October 27. The existing
operator-confirmed bootstrap administrator is reused; this change appoints nobody.
The inventory covers verified accounts observed by the portal. It is not the full
Relcom ID pool, and it contains no password, email, raw provider subject or token.
An optional profile name is stored privately from the trusted session, shown as a
profile label, and never replaces the stable keyed project pseudonym. Public RFC
comments retain their existing pseudonyms. Legal identity is not asserted.

## Operations and bounds

- `GET /community/v1/members`: admin-only, up to 50 members/page; opaque actor
  cursor, literal bounded search and active/blocked filter. Response fits the
  fixed private proxy limit and carries no-store through both proxies.
- Existing `POST /community/v1/roles`: admin-only grant/revoke of moderator,
  maintainer or admin; only an already enrolled participant, with a reason.
- `POST /community/v1/members/{project-pseudonym}/access`: admin-only reversible
  block/restore with a reason. Self-block and blocking the pinned bootstrap owner
  are refused. Granting another role to a blocked participant is refused.
- Existing moderation and private audit pages are exposed through the same admin
  screen. Every successful mutation uses a stable idempotency key and audit record.

A block removes effective portal privileges immediately on every request, including
replays of cached privileged mutations. Public research remains readable as for an
anonymous visitor; private pending material does not. The identity-provider account
and its sign-in session remain intact, so the participant can still sign out or
manage that separate account. Restore re-enables the previously stored portal roles.
Portal roles do not allocate formal RFC votes, approve a GitHub PR, admit an agent
or grant model/infrastructure access. Maintainer is presently an attributed role,
not a new execution capability.

The SQLite migration adds `member_state` without rewriting existing users, roles,
entries or sessions. State stays under the existing private service directory and
never enters the public exporter or download bundles. A backend downgrade that
predates blocking is not an acceptable enforcement rollback while suspensions exist;
retain an access-aware backend or use an explicitly reviewed maintenance procedure.

Both application proxy allowlists and the IPvX-only ingress allowlist must include
the two member paths before production acceptance. No broad proxy, new secret,
identity-provider administrator token or infrastructure permission is introduced.
Publication still requires protected-main review and the exact pinned release.

## Verification and preview

`test_admin.py` checks privacy, pagination/literal search, replay denial after block,
private visibility, protected owner/self-block, restore and one audited effect on
retry. `test_community_adapter.py` exercises the actual two HTTP proxies with signed
synthetic sessions. `browser_admin_check.mjs` covers four widths, ordinary-user
denial, selection/pagination, malformed committed response retry, block/restore,
plain text and clearing private data after revocation.

`scripts/admin_demo.py` is a separate loopback-only synthetic preview on port 8097.
It uses a temporary community database and an explicitly labeled synthetic admin,
not a real login bypass. It is not imported by production, installed by the service
or included in the public export. The preview banner warns that changes touch only
test users. Never point that program at a real community state directory or bind
it outside loopback. Live acceptance must separately use the real approved account.

## Social registration clarification

The provider's existing `login/idp-routes.ts` handles both an existing link and new
account creation when project sign-up is enabled. Its email/password registration
form omits the social buttons; those are on the login page. The portal explains
that a first Google/Apple/Telegram sign-in may create the account, with separate
email proof for Telegram when needed. No new provider credential or shared identity
service deployment is part of this change. The owner's screenshots show the three
buttons; they do not independently establish every provider's completed callback.
