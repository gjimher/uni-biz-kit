from .. import dev_ports

_TEMPLATE = r"""import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import mdx from '@mdx-js/rollup';
import remarkFrontmatter from 'remark-frontmatter';
import remarkMdxFrontmatter from 'remark-mdx-frontmatter';

export default defineConfig(() => {
  return {
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
    },
  };
});
"""


def generate() -> str:
    return _TEMPLATE.replace('__FRONTEND_PORT__', str(dev_ports.FRONTEND))
