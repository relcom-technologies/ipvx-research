# Existing IPvX infrastructure

Owner-selected deployment on 2026-10-27: reuse proj-ipvx-agent-lab, without a new VM, Resources subscription, public NIC or lab API exposure. The website is ordinary HTTP/HTTPS over IP; native agent experiments are a separate network.

The relcom-infra deployment manifest pins this repository's full commit and source archive SHA-256. Its scoped manual workflow verifies both before transferring the source over the existing pinned CI SSH path. `install.sh` runs only on the existing observer, copies HTML/assets/public data/RFCs into a separate version directory, and installs a restricted DynamicUser service at 10.10.50.131:8092. It does not touch the existing controller, model services or identity directories.

The file handler refuses directory listing, dot paths, parent traversal and symlink releases. It provides `/healthz` and an X-IPvX-Revision response header. The public data and verifier are deliberately downloadable. Visitor request contents and addresses are not logged by this handler.

The owner additionally authorized Relcom ID sign-in and a Relcom Press blog. Four exact `/auth/` routes proxy only to a separate authentication process on `127.0.0.1:8094`. Only logout accepts POST. The file service retains its outbound network restriction, with loopback added for that fixed proxy. The separate authentication service uses the pinned Relcom ID HTTPS issuer; it has no laboratory files, raw sockets or model access. Public OIDC client/pool identifiers are configured in the installer; no client secret exists. The service creates its own encrypted session state in a systemd-managed private StateDirectory. This state and the authentication source are never part of the public export. See [integration contract](../docs/integrations-relcom.md).

Authentication confirms an email account, not legal identity, project membership, votes or native-network admission. Reading the research stays public. The blog uses the free Press platform address and a public feed; its external request is allowed explicitly by CSP. There is no automatic article generation or paid model key. Attributed research history and draft RFC-0005 are public documents; adding a draft does not ratify it.

The infrastructure route maps only ipvx.org and www.ipvx.org to that listener. Standard Cloudflare proxy and Full (strict) TLS are required by the existing ingress policy. Preserve the IONOS mail, SPF, DKIM and autodiscover records when moving authoritative DNS. Do not disable the ingress firewall or publish experiment ports.

After deployment, verify the exact revision through the internal health endpoint and publicly valid HTTPS, then check the report, saved trace and participation form. A first publication also needs the DNS change; a local preview or an internal 200 response is not public acceptance.

For rollback, the operator selects an existing reviewed source revision in relcom-infra, with its matching archive digest, and runs the same scoped deployment. Previous `/srv/ipvx-research/releases/<commit>` directories remain available. No voting workflow deploys the service.

Session state is separate from releases. Its SQLite database and encryption key must be kept together under the private StateDirectory, and must never enter a source ZIP, public data or an acceptance artifact. Sessions have a one-hour maximum lifetime; a rollback that changes the OIDC pool/client does not reuse their authorization. The existing native testbed is untouched by portal deployment.
