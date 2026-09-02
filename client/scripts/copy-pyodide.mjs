// Copies the Pyodide runtime files out of node_modules into public/pyodide/
// so Vite serves them at /pyodide/* in dev and bundles them into dist/ on
// build. Runs as `predev` / `prebuild` (see package.json). Self-hosted so
// there's no CDN dependency and the wasm/worker stay same-origin.
import { cpSync, existsSync, mkdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..', 'node_modules', 'pyodide');
const dest = join(here, '..', 'public', 'pyodide');

const FILES = [
  'pyodide.mjs',
  'pyodide.asm.js',
  'pyodide.asm.wasm',
  'python_stdlib.zip',
  'pyodide-lock.json',
];

if (!existsSync(src)) {
  console.error('[copy-pyodide] node_modules/pyodide not found — run `npm i` first');
  process.exit(1);
}

// Skip if already up to date (pyodide.asm.wasm is the big one).
const marker = join(dest, 'pyodide.asm.wasm');
if (existsSync(marker) && statSync(marker).size === statSync(join(src, 'pyodide.asm.wasm')).size) {
  process.exit(0);
}

mkdirSync(dest, { recursive: true });
for (const f of FILES) cpSync(join(src, f), join(dest, f));
console.log(`[copy-pyodide] copied ${FILES.length} files to public/pyodide/`);
