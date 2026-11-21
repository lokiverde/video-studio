// Render chosen frames of a composition as PNG stills, once per props variant, from ONE
// bundle and ONE browser. `npx remotion still` re-bundles on every call, which is fine for
// a 30 frame contact sheet and far too slow for the hundreds of frames caption QC reads.
//
//   node qc-stills.mjs <manifest.json>
//
// manifest: {composition, publicDir, outDir, scale, frames: [n...], variants: {name: propsPath}}
// writes <outDir>/<variant>/<frame>.png for every variant and frame.
import {readFileSync, mkdirSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {openBrowser, renderStill, selectComposition} from '@remotion/renderer';

const PARALLEL = 4;

const manifest = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const here = path.dirname(fileURLToPath(import.meta.url));
const serveUrl = await bundle({entryPoint: path.join(here, 'src/index.ts'), publicDir: manifest.publicDir});
const browser = await openBrowser('chrome');
try {
  for (const [name, propsPath] of Object.entries(manifest.variants)) {
    const inputProps = JSON.parse(readFileSync(propsPath, 'utf8'));
    const composition = await selectComposition({serveUrl, id: manifest.composition, inputProps, puppeteerInstance: browser});
    const dir = path.join(manifest.outDir, name);
    mkdirSync(dir, {recursive: true});
    const queue = [...manifest.frames];
    const still = (frame) => renderStill({composition, serveUrl, inputProps, frame, scale: manifest.scale ?? 1, imageFormat: 'png',
      output: path.join(dir, `${String(frame).padStart(6, '0')}.png`), puppeteerInstance: browser, logLevel: 'error'});
    const worker = async () => {
      while (queue.length) {
        const frame = queue.shift();
        // a parallel page now and then loses its video frame fetch; one retry clears it
        await still(frame).catch(() => still(frame));
      }
    };
    await Promise.all(Array.from({length: PARALLEL}, worker));
  }
} finally {
  await browser.close({silent: true});
}
