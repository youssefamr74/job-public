// Fails when a build (dist/ by default) contains MSW, the demo code or its sample data.
// `node scripts/check-build.mjs dist-demo` must fail: that's how to see the check works.
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const MARKERS = ['mockServiceWorker', '[MSW]', 'Larkspur Analytics', 'Demo with sample data', 'Not available in the demo'];
const dir = process.argv[2] ?? 'dist';

function files(path) {
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? files(join(path, entry.name)) : [join(path, entry.name)],
  );
}

const found = files(dir).flatMap((file) => {
  const text = readFileSync(file, 'latin1');
  return MARKERS.filter((marker) => text.includes(marker)).map((marker) => `${file}: ${marker}`);
});

if (found.length) {
  console.error(`${dir} contains demo code:\n${found.join('\n')}`);
  process.exit(1);
}
console.log(`${dir} has no demo code.`);
