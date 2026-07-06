"""Render the Caddyfile for the proxy stack.

The site is served over HTTPS on `domain`. The certificate is obtained via ACME
TLS-ALPN-01 only: the HTTP-01 challenge is disabled and the HTTP->HTTPS
redirect vhost is not set up, so nothing depends on port 80 being reachable
(only 443 is forwarded through the NAT to the production host).

Each proxied app is reverse-proxied at its own base_uri, preserving the path
prefix: the app's own nginx already serves the SPA under that prefix and proxies
its own <base_uri>/api, so a plain prefix-preserving reverse_proxy is enough.
The app frontends publish 0.0.0.0:<port>:80 on the host. The Caddy container
runs with host networking, so it reaches them through 127.0.0.1:<port>.
"""


def generate(ctx) -> str:
    global_email = f"\n\temail {ctx.acme_email}" if ctx.acme_email else ""

    routes = []
    for target in ctx.targets:
        prefix = target["base_uri"].rstrip("/")  # e.g. "/b2c"
        port = target["port"]
        routes.append(f"\tredir {prefix} {prefix}/ 308")
        routes.append(f"\treverse_proxy {prefix}/* 127.0.0.1:{port}")
    routes_block = "\n".join(routes)

    return f"""\
{{
	# Only 443 is reachable through the NAT: disable the port-80 redirect vhost.
	auto_https disable_redirects{global_email}
}}

{ctx.domain} {{
	# Certificate via ACME TLS-ALPN-01 only (runs on 443); HTTP-01 needs port 80.
	tls {{
		issuer acme {{
			disable_http_challenge
		}}
	}}

	encode gzip
	root * /srv/site

{routes_block}

	file_server
}}
"""
