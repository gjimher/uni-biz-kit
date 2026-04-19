def generate() -> str:
    return """import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'REACT_APP_');
  const processEnv = Object.fromEntries(
    Object.entries(env).map(([k, v]) => [`process.env.${k}`, JSON.stringify(v)])
  );
  return {
    plugins: [react()],
    define: processEnv,
    resolve: {
      alias: [
        {
          find: /^@mui\\/icons-material\\/(.+)/,
          replacement: '@mui/icons-material/esm/$1',
        },
        {
          find: '@mui/icons-material',
          replacement: '@mui/icons-material/esm',
        },
      ],
    },
    server: {
      port: parseInt(process.env.PORT) || 3000,
      open: false,
    },
  };
});
"""
