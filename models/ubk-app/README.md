# UBK App — Landing Page & Reverse Proxy

Not a generated application — a **proxy-kind model**. It has no concepts, security or backend of its own: just [`deployment.jsonc`](deployment.jsonc), the landing page [`index.md`](index.md) and its [`assets/`](assets).

On deploy it produces a single **Caddy** container that terminates HTTPS for `www.unibizkit.dev`, serves the landing page, and reverse-proxies the demo apps ([b2c-app](../b2c-app/README.md), [intranet-app](../intranet-app/README.md)) under their respective `base_uri` paths — so several independently generated apps share one domain. See [Deployment.md](../../docs/Deployment.md).
