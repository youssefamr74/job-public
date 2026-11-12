/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';
import type { IncomingMessage } from 'node:http';
import { createRequire } from 'node:module';
import type { Plugin } from 'vite';

const backend = 'http://127.0.0.1:8000';

const apiPrefixes = [
  '/users',
  '/setup',
  '/mail',
  '/applications',
  '/analytics',
  '/companion',
  '/goals',
  '/cv',
  '/debug',
  '/ai',
  '/opportunities',
  '/sync',
  '/notifications',
  '/data',
  '/settings',
  '/health',
  '/docs',
  '/openapi.json',
];

const apiPages = ['/docs', '/openapi.json', '/mail/oauth/', '/data/export/'];

// Page paths and API paths overlap (/applications is both), the same way the backend decides:
// a browser navigation asking for HTML gets the web app, everything else goes to the API.
function bypass(req: IncomingMessage): string | undefined {
  const url = req.url ?? '';
  if (apiPages.some((page) => url.startsWith(page))) return undefined;
  if (req.method === 'GET' && (req.headers.accept ?? '').includes('text/html')) return '/index.html';
  return undefined;
}

/** The demo answers API calls in the browser with MSW, which needs its service worker file next to the page. */
function mswWorker(): Plugin {
  const source = () => readFileSync(createRequire(import.meta.url).resolve('msw/mockServiceWorker.js'), 'utf8');
  return {
    name: 'msw-worker',
    configureServer(server) {
      server.middlewares.use('/demo/mockServiceWorker.js', (_req, res) => {
        res.setHeader('Content-Type', 'text/javascript');
        res.end(source());
      });
    },
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'mockServiceWorker.js', source: source() });
    },
  };
}

// `--mode demo` builds the static demo for /demo/ with sample data. Every other build leaves out
// the demo code: __DEMO__ is false there, so the import of src/demo/ is removed.
export default defineConfig(({ mode }) => ({
  plugins: mode === 'demo' ? [react(), mswWorker()] : [react()],
  base: mode === 'demo' ? '/demo/' : '/',
  define: { __DEMO__: JSON.stringify(mode === 'demo') },
  build: { chunkSizeWarningLimit: 800, outDir: mode === 'demo' ? 'dist-demo' : 'dist' },
  server: {
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(apiPrefixes.map((prefix) => [prefix, { target: backend, bypass }])),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
  },
}));
