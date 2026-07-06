"""Render the landing page (index.md) to a self-contained static HTML file.

Uses the pure-Python `markdown` library (no node toolchain). The output is a
single HTML document with embedded CSS, served as-is by Caddy's file_server.
"""
import markdown

_CSS = """\
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6;
  max-width: 46rem;
  margin: 0 auto;
  padding: 2.5rem 1.25rem 4rem;
  color: #1a1a1a;
  background: #ffffff;
}
h1 { font-size: 2rem; line-height: 1.2; margin: 0 0 0.5rem; }
h2 { margin-top: 2.5rem; border-bottom: 1px solid #e5e5e5; padding-bottom: 0.3rem; }
h3 { margin-top: 2rem; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 1rem 0;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
}
code {
  background: #f3f4f6;
  padding: 0.15em 0.35em;
  border-radius: 4px;
  font-size: 0.9em;
}
pre { background: #f3f4f6; padding: 1rem; border-radius: 8px; overflow-x: auto; }
pre code { background: none; padding: 0; }
hr { border: none; border-top: 1px solid #e5e5e5; margin: 2.5rem 0; }
footer { margin-top: 3rem; color: #6b7280; font-size: 0.9rem; }
@media (prefers-color-scheme: dark) {
  body { color: #e5e7eb; background: #0d1117; }
  h2 { border-bottom-color: #21262d; }
  a { color: #58a6ff; }
  img { border-color: #21262d; }
  code, pre { background: #161b22; }
  hr { border-top-color: #21262d; }
  footer { color: #8b949e; }
}
"""


def render(md_text: str, title: str) -> str:
    body = markdown.markdown(md_text, extensions=["extra"])
    return f"""\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{_CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""
