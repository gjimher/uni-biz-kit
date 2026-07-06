from .context import Context


def generate(ctx: Context) -> str:
    locale = ctx.presentation_config["locale"]
    title = ctx.presentation_config["html_head_title"]
    return f"""<!DOCTYPE html>
<html lang="{locale}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#000000" />
    <title>{title}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/index.jsx"></script>
  </body>
</html>"""
