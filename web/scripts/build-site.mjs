// Puts the static site together in ../_site: the landing page (site/), the demo build (dist-demo/)
// under /demo/, and the fonts the landing page uses. Run `npm run build:demo` first.
import { cpSync, existsSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(web, '..', '_site');
const require = createRequire(import.meta.url);

if (!existsSync(join(web, 'dist-demo', 'index.html'))) {
  console.error('No demo build in dist-demo/. Run `npm run build:demo` first.');
  process.exit(1);
}

rmSync(out, { recursive: true, force: true });
cpSync(join(web, '..', 'site'), out, { recursive: true });
cpSync(join(web, 'public', 'favicon.svg'), join(out, 'favicon.svg'));
cpSync(join(web, 'dist-demo'), join(out, 'demo'), { recursive: true });

const fonts = [
  ['@fontsource/ibm-plex-sans', 'ibm-plex-sans', [400, 500, 600]],
  ['@fontsource/ibm-plex-mono', 'ibm-plex-mono', [400]],
];
for (const [pkg, name, weights] of fonts) {
  const files = join(dirname(require.resolve(`${pkg}/package.json`)), 'files');
  for (const weight of weights) {
    cpSync(join(files, `${name}-latin-${weight}-normal.woff2`), join(out, 'fonts', `${name}-${weight}.woff2`));
  }
}
console.log(`Site written to ${out}`);
