from .. import dev_ports

_TEMPLATE = r"""import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import mdx from '@mdx-js/rollup';
import remarkFrontmatter from 'remark-frontmatter';
import remarkMdxFrontmatter from 'remark-mdx-frontmatter';

export default defineConfig(() => {
  return {
    base: '__BASE_URI__',
    plugins: [
      {
        enforce: 'pre',
        ...mdx({
          remarkPlugins: [remarkFrontmatter, remarkMdxFrontmatter],
          providerImportSource: '@mdx-js/react',
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
