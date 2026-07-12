from .. import dev_ports

_TEMPLATE = r"""import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import mdx from '@mdx-js/rollup';
import remarkFrontmatter from 'remark-frontmatter';
import remarkMdxFrontmatter from 'remark-mdx-frontmatter';

export default defineConfig(({ command }) => {
  return {
    base: '__BASE_URI__',
    plugins: [
      {
        enforce: 'pre',
        ...mdx({
          remarkPlugins: [remarkFrontmatter, remarkMdxFrontmatter],
          providerImportSource: '@mdx-js/react',
          // MDX picks the jsx runtime from Vite's *mode*, but React resolves
          // react/jsx-dev-runtime from process.env.NODE_ENV, which `vite build`
          // keeps as "production" even with `--mode development`. That bundles
          // the production stub (jsxDEV = undefined) under MDX's jsxDEV calls
          // and every MDX page crashes at render. Follow the command instead:
          // only the dev server may use the dev runtime.
          development: command === 'serve',
        }),
      },
      react(),
    ],
    resolve: {
      alias: [
        {
          find: /^@mui\/icons-material\/(.+)/,
          replacement: '@mui/icons-material/esm/$1',
        },
        {
          find: '@mui/icons-material',
          replacement: '@mui/icons-material/esm',
        },
      ],
    },
    server: {
      port: parseInt(process.env.PORT) || __FRONTEND_PORT__,
      open: false,
      proxy: {
        '__API_PROXY_PATH__': {
          target: 'http://localhost:__SUPABASE_PORT__',
          rewrite: (path) => path.replace(/^__API_PROXY_PATH_RE__/, ''),
          changeOrigin: true,
        },
      },
    },
    // Mirror the /api -> Kong proxy for `vite preview` so the production build is
    // served same-origin (the app resolves VITE_SUPABASE_URL against its origin).
    preview: {
      proxy: {
        '__API_PROXY_PATH__': {
          target: 'http://localhost:__SUPABASE_PORT__',
          rewrite: (path) => path.replace(/^__API_PROXY_PATH_RE__/, ''),
          changeOrigin: true,
        },
      },
    },
  };
});
"""


def generate(base_uri: str = "/") -> str:
    # base_uri always ends with / (normalized by SchemaProcessor)
    # Proxy key: /api for root, /<base>/api for subpaths (e.g. /test/api)
    base_prefix = base_uri.rstrip("/")  # "" or "/test"
    api_proxy_path = base_prefix + "/api"  # "/api" or "/test/api"
    api_proxy_path_re = api_proxy_path.replace("/", r"\/")
    return (
        _TEMPLATE
        .replace('__FRONTEND_PORT__', str(dev_ports.FRONTEND))
        .replace('__SUPABASE_PORT__', str(dev_ports.SUPABASE_API))
        .replace('__BASE_URI__', base_uri)
        .replace('__API_PROXY_PATH_RE__', api_proxy_path_re)
        .replace('__API_PROXY_PATH__', api_proxy_path)
    )
