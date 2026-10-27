# Existing IPvX infrastructure

Owner-selected deployment on 2026-10-27: reuse proj-ipvx-agent-lab, without a new VM, Resources subscription, public NIC or lab API exposure. The website is ordinary HTTP/HTTPS over IP; native agent experiments are a separate network.

The relcom-infra deployment manifest pins this repository's full commit and source archive SHA-256. Its scoped manual workflow verifies both before transferring the source over the existing pinned CI SSH path. `install.sh` runs only on the existing observer, copies HTML/assets/public data/RFCs into a separate version directory, and installs a restricted DynamicUser service at 10.10.50.131:8092. It does not touch the existing controller, model services or identity directories.

The static handler has no POST, model execution, authentication, proxy or lab control endpoint. It refuses directory listing, dot paths, parent traversal and symlink releases. It provides `/healthz` and an X-IPvX-Revision response header. The public data and verifier are deliberately downloadable. Visitor request contents and addresses are not logged by this handler.

The infrastructure route maps only ipvx.org and www.ipvx.org to that listener. Standard Cloudflare proxy and Full (strict) TLS are required by the existing ingress policy. Preserve the IONOS mail, SPF, DKIM and autodiscover records when moving authoritative DNS. Do not disable the ingress firewall or publish experiment ports.

After deployment, verify the exact revision through the internal health endpoint and publicly valid HTTPS, then check the report, saved trace and participation form. A first publication also needs the DNS change; a local preview or an internal 200 response is not public acceptance.

For rollback, the operator selects an existing reviewed source revision in relcom-infra, with its matching archive digest, and runs the same scoped deployment. Previous `/srv/ipvx-research/releases/<commit>` directories remain available. No voting workflow deploys the service.
