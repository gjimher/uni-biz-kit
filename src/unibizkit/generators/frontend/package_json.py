def generate(ctx) -> str:
    # The markdown editor is a heavy dependency: include it only when used.
    markdown_dep = ""
    if any(f["type"] == "markdown" for c in ctx.concepts for f in c["fields"]):
        markdown_dep = '\n    "@uiw/react-md-editor": "^4.0.5",'

    return f"""{{
  "name": "unibizkit-react-admin",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "dependencies": {{
    "@mdx-js/react": "^3.0.0",
    "@mui/material": "^5.16.12",
    "@mui/icons-material": "^5.16.12",
    "@supabase/supabase-js": "^2.89.0",{markdown_dep}
    "papaparse": "^5.4.1",
    "react": "18.2.0",
    "react-admin": "^5.14.0",
    "react-dom": "18.2.0",
    "react-router-dom": "^6.0.0",
    "ra-supabase": "^3.5.2",
    "@hello-pangea/dnd": "^16.5.0"
  }},
  "scripts": {{
    "start": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint src/ --ext .js,.jsx --max-warnings 0",
    "lint:fix": "eslint src/ --ext .js,.jsx --fix"
  }},
  "devDependencies": {{
    "@mdx-js/rollup": "^3.0.0",
    "remark-frontmatter": "^5.0.0",
    "remark-mdx-frontmatter": "^4.0.0",
    "vite": "^5.4.0",
    "@vitejs/plugin-react": "^4.3.0",
    "eslint": "^8.57.0",
    "eslint-plugin-react": "^7.34.1"
  }}
}}"""
