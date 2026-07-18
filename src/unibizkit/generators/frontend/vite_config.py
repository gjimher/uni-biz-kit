from .. import dev_ports

_TEMPLATE = r"""import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import mdx from '@mdx-js/rollup';
import remarkFrontmatter from 'remark-frontmatter';
import remarkMdxFrontmatter from 'remark-mdx-frontmatter';
__CUSTOM_PLUGIN_SECTION__export default defineConfig(({ command }) => {
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
__CUSTOM_PLUGIN_ENTRY__    ],
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


_CUSTOM_PLUGIN_SECTION = r"""import fs from 'node:fs';
import path from 'node:path';

// --- Presentation customization dev endpoint (dev server only) --------------
// Lets the in-app design mode read and save the model's
// presentation-custom-NN.jsonc overlay files. The model directory is embedded
// at generation time; the plugin is inert in builds (apply: 'serve') and file
// names are strictly whitelisted, so no other path can be read or written.
const UBK_MODEL_DIR = '__MODEL_DIR__';
const UBK_CUSTOM_FILE_RE = /^presentation-custom-(\d{2})\.jsonc$/;
const UBK_CUSTOM_SECTIONS = ['$schema', 'description', 'roles', 'menu', 'lists', 'forms', 'labels', 'workflow_states'];

// Good-enough JSONC comment stripper for overlay files (string-aware).
const stripJsonc = (text) =>
  text.replace(/("(?:[^"\\]|\\.)*")|\/\/[^\n]*|\/\*[\s\S]*?\*\//g, (match, str) => str ?? '');

const ubkPresentationCustom = () => ({
  name: 'ubk-presentation-custom',
  apply: 'serve',
  configureServer(server) {
    server.middlewares.use('/__ubk/presentation-custom', (req, res) => {
      const send = (code, body) => {
        res.statusCode = code;
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify(body));
      };
      try {
        if (req.method === 'GET') {
          const files = fs.readdirSync(UBK_MODEL_DIR).filter((f) => UBK_CUSTOM_FILE_RE.test(f)).sort();
          return send(200, {
            files,
            overlays: files.map((file) => ({
              file,
              order: parseInt(UBK_CUSTOM_FILE_RE.exec(file)[1], 10),
              ...JSON.parse(stripJsonc(fs.readFileSync(path.join(UBK_MODEL_DIR, file), 'utf8'))),
            })),
          });
        }
        if (req.method === 'PUT') {
          let body = '';
          req.on('data', (chunk) => { body += chunk; });
          req.on('end', () => {
            try {
              const { file, content, previousFile, overwrite } = JSON.parse(body);
              if (typeof file !== 'string' || !UBK_CUSTOM_FILE_RE.test(file)) {
                return send(400, { error: 'File name must match presentation-custom-NN.jsonc' });
              }
              if (previousFile !== null && previousFile !== undefined
                  && (typeof previousFile !== 'string' || !UBK_CUSTOM_FILE_RE.test(previousFile))) {
                return send(400, { error: 'Previous file name must match presentation-custom-NN.jsonc' });
              }
              // Structural check only: the authoritative validation happens in
              // the generator (SchemaLoader) like for every other model file.
              const parsed = JSON.parse(stripJsonc(content));
              const unknown = Object.keys(parsed).filter((key) => !UBK_CUSTOM_SECTIONS.includes(key));
              if (unknown.length) return send(400, { error: `Unknown sections: ${unknown.join(', ')}` });
              if (parsed.roles !== undefined && !Array.isArray(parsed.roles)) {
                return send(400, { error: 'roles must be an array of role names' });
              }
              const targetPath = path.join(UBK_MODEL_DIR, file);
              const previousPath = previousFile ? path.join(UBK_MODEL_DIR, previousFile) : null;
              if (fs.existsSync(targetPath) && file !== previousFile && overwrite !== true) {
                return send(409, { error: `${file} already exists` });
              }
              if (previousPath && previousFile !== file && !fs.existsSync(previousPath)) {
                return send(409, { error: `${previousFile} no longer exists` });
              }
              fs.writeFileSync(targetPath, content, 'utf8');
              if (previousPath && previousFile !== file) fs.unlinkSync(previousPath);
              return send(200, { ok: true });
            } catch (error) {
              return send(400, { error: String((error && error.message) || error) });
            }
          });
          return;
        }
        send(405, { error: 'Method not allowed' });
      } catch (error) {
        send(500, { error: String((error && error.message) || error) });
      }
    });
  },
});

"""


def generate(base_uri: str = "/", model_dir: str = "") -> str:
    # base_uri always ends with / (normalized by SchemaProcessor)
    # Proxy key: /api for root, /<base>/api for subpaths (e.g. /test/api)
    base_prefix = base_uri.rstrip("/")  # "" or "/test"
    api_proxy_path = base_prefix + "/api"  # "/api" or "/test/api"
    api_proxy_path_re = api_proxy_path.replace("/", r"\/")
    # An empty model_dir means the customization system is off (designer 'off'):
    # the dev endpoint plugin is not emitted at all.
    if model_dir:
        plugin_section = _CUSTOM_PLUGIN_SECTION.replace(
            '__MODEL_DIR__', model_dir.replace("\\", "\\\\").replace("'", "\\'")
        )
        plugin_entry = "      ubkPresentationCustom(),\n"
    else:
        plugin_section = "\n"
        plugin_entry = ""
    return (
        _TEMPLATE
        .replace('__CUSTOM_PLUGIN_SECTION__', plugin_section)
        .replace('__CUSTOM_PLUGIN_ENTRY__', plugin_entry)
        .replace('__FRONTEND_PORT__', str(dev_ports.FRONTEND))
        .replace('__SUPABASE_PORT__', str(dev_ports.SUPABASE_API))
        .replace('__BASE_URI__', base_uri)
        .replace('__API_PROXY_PATH_RE__', api_proxy_path_re)
        .replace('__API_PROXY_PATH__', api_proxy_path)
    )
