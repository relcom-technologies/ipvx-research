# Relcom ID and Press integration

Integration contract checked on 2026-10-27 against Relcom ID main
`083e74c3105d4aa0cbd1e324103cb4b3bbec64b9` and Relcom Press main
`6e25f2c99a217c0911b5c68af9320c98377dc696`. Public OAuth discovery was read from both
production origins with ordinary CA-verified HTTPS. This document is implementation
guidance, not a receipt of a successful production user sign-in.

## Identity

The site's public PKCE application is registered in the IPvX Research project:

- Issuer: `https://id.relcom.com`.
- Public client ID: `396952476441378818`.
- User pool / organization: `396952378110115842`.
- Exact callback: `https://ipvx.org/auth/callback`.
- Exact post-logout URI: `https://ipvx.org/account.html`.
- No client secret exists or is required. Developer accounts and project users are
  separate pools; a console sign-in does not prove that a project-user sign-in works.

`infra/auth.py` uses Authlib's authorization-code client with PKCE S256. Authlib and
joserfc verify the signed ID token, issuer, audience, lifetime and nonce; the site
additionally requires the exact pool, a subject, an email and `email_verified=true`.
The site does not collect passwords and does not claim legal identity or KYC.

Install the exact runtime dependency set into the dedicated identity environment:

```sh
python3 -m venv /srv/ipvx-research/auth-venv
/srv/ipvx-research/auth-venv/bin/pip install -r infra/auth-requirements.lock
```

The service needs Python 3.11 or later for the pinned cryptography runtime. Supply
these non-secret settings through the scoped service environment:

```text
RELCOM_ID_CLIENT_ID=396952476441378818
RELCOM_ID_ORG_ID=396952378110115842
IPVX_AUTH_STATE_DIR=/var/lib/ipvx-research-auth/state
```

Run `infra/auth.py` with that environment. It binds only `127.0.0.1:8094`.
The existing static service must proxy only the four exact endpoints `/auth/login`,
`/auth/callback`, `/auth/session`, and `/auth/logout`, keeping the original canonical
Host, Cookie and Origin and every separate Set-Cookie header. Unknown `/auth/*`
paths and all lab/API paths remain unavailable. Do not use request-supplied URLs as
proxy targets. Redirect visitors from www to the canonical origin before sign-in.

The static service can retain its public-network egress restriction; grant it only
loopback access to the fixed identity listener. The identity service needs normal
HTTPS egress to the pinned issuer for token exchange, keys and userinfo. It does not
need another public listener or shared firewall change. Its StateDirectory is
private and writable; the public release directory remains read-only.

The generated 0600 Fernet key and 0600 SQLite database stay in a 0700 service state
directory, outside the public export and Git. The `state` child is intentional:
systemd may expose the DynamicUser StateDirectory itself through a managed symlink;
the application rejects a symlink as its final state directory or key/database.
Cookies are random opaque references,
stored by hash; provider credentials and profile data are encrypted at rest using
the standard cryptography library. Cookies are host-only, Secure, HttpOnly,
SameSite=Lax, with a `__Host-` prefix and Path=/. Transaction state is one-use,
including concurrent callbacks, and expires after ten minutes. A changed client or
pool invalidates prior state. Local sessions expire within one hour; no refresh
tokens or `offline_access` scope are requested. Userinfo is rechecked after ten
minutes; a refusal clears the session, while an outage returns a retryable 503.

`GET /auth/session` returns only the authenticated flag, verified public profile and
the explicit statement that sign-in grants no research membership. It never returns
provider credentials. `POST /auth/logout` requires Origin exactly
`https://ipvx.org`, deletes the local session and redirects through Relcom ID's
standard end-session endpoint with a server-stored ID-token hint. GET logout is
refused. The final return address is the exact registered account page.

There is no grant of RFC voting rights, model execution, publication, infrastructure
access or admission from this sign-in. Existing governance approval remains separate.

Synthetic tests use a real RSA key and real JOSE verification, with no production
mail or accounts:

```sh
python scripts/test_auth.py
```

Production acceptance must separately record registration or invitation completion,
verified sign-in, the returning session and logout. Do not save tokens, codes,
cookies, private profiles or password-reset links in that receipt.

## Press

The independent official MCP endpoint is `https://press.relcom.com/mcp`. Discovery
uses `/.well-known/oauth-authorization-server` and
`/.well-known/oauth-protected-resource/mcp`. `/oauth/register` registers a public
software client with exact redirects and token endpoint authentication `none`.
Authorize with PKCE S256, the MCP resource and minimal `press:read press:manage`
permissions. Consent selects one existing blog or authorizes one new blog in the
owner's workspace. `get_blog` must precede mutations. `create_blog` binds that
connection to one blog and never purchases a plan. `connect_website` adds a public
HTTPS origin without removing existing origins and returns a public integration kit.

Free currently permits one blog and one locale at its platform address
`<handle>.press.relcom.org`. A custom domain or `/blog` reverse-proxy mount consumes
a non-platform address allowance; do not enable one if it requires a new paid plan.
The portal can display the free blog using its public content feed and link to its
hosted articles. Register `https://ipvx.org` and `https://www.ipvx.org` in the blog's
allowed origins. Public article reading needs no API key or private connector token.

```text
GET https://press.relcom.com/embed/v1/sites/<siteId>/latest?locale=ru&limit=5&kind=article
GET https://press.relcom.com/api/v1/sites/<siteId>/articles?locale=ru&kind=article
```

The official embed script inserts a Shadow DOM style element. A local, ordinary
script rendering the public feed with textContent and the portal's own stylesheet
keeps its strict self-only script/style policy. Allow the exact Press origin in
connect-src for browser fetching. Explicitly show an empty/error state; the official
widget intentionally renders nothing for an empty blog. Do not put the management
API key or connector credentials in public files. Drafting and article publication
are separate actions; publication requires an explicit instruction and the separate
`press:publish` permission.

Reader comments, if later requested, have their own verified reader client and pool
configuration in Press Settings, separate from staff membership. Embedded/headless
commenting is outside the current Press reader feature. Do not claim that portal
sign-in automatically signs a visitor into a separately hosted Press blog.
