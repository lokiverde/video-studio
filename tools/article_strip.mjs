// Captures passages of a web article at phone width, for an army split beat's
// `portraitShot`: whole lines in big type, where cropping a wide snapshot slices words.
//
//   node tools/article_strip.mjs spec.json
//
// spec.json:
//   {"url": "...", "out_dir": "jobs/<id>/public/<topic>",
//    "width": 390, "scale": 3,                      // CSS px viewport, device pixel ratio
//    "before": "js",                                // optional, runs after load (open collapsed sections)
//    "strips": [{"name": "02_holding_9x16",
//                "para": "text inside the paragraph",
//                "from": "text on the strip's first line",
//                "to": "text on the strip's last line",
//                "marks": ["phrase to highlight", ...]}]}
//
// Prints one JSON line per strip with its file and the `portraitHighlight` boxes, in the
// PNG's pixels, ready to paste into the beat. Runs Chrome headless on its own profile.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333;
const PAD_X = 10;   // CSS px beside the paragraph
const PAD_Y = 3;    // CSS px above/below; more catches the next line's descenders

const spec = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const width = spec.width ?? 390;
const scale = spec.scale ?? 3;
fs.mkdirSync(spec.out_dir, { recursive: true });

const profile = fs.mkdtempSync(path.join(os.tmpdir(), "article-strip-"));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function pageTarget() {
  for (let i = 0; i < 50; i++) {
    try {
      const page = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find((t) => t.type === "page");
      if (page) return page;
    } catch { /* Chrome still starting */ }
    await sleep(200);
  }
  throw new Error(`Chrome did not open its debugging port ${PORT}`);
}

function connect(url) {
  const ws = new WebSocket(url);
  let id = 0;
  const pending = new Map();
  const waiters = [];
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
    } else if (msg.method) {
      waiters.filter((w) => w.method === msg.method).forEach((w) => w.resolve(msg.params));
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const n = ++id;
    pending.set(n, { resolve, reject });
    ws.send(JSON.stringify({ id: n, method, params }));
  });
  const once = (method) => new Promise((resolve) => waiters.push({ method, resolve }));
  const opened = new Promise((r) => ws.addEventListener("open", r, { once: true }));
  return { ws, send, once, opened };
}

// In the page: the smallest block holding `para`, and a Range over a phrase inside it.
const HELPERS = `
  const paraOf = (s) => [...document.querySelectorAll('p, li, blockquote, div')]
    .filter(e => e.innerText && e.innerText.includes(s)).sort((a, b) => a.innerText.length - b.innerText.length)[0];
  const rangeOf = (root, phrase) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = []; let text = '';
    while (walker.nextNode()) { nodes.push([walker.currentNode, text.length]); text += walker.currentNode.data; }
    const at = text.indexOf(phrase);
    if (at < 0) return null;
    const pos = (off) => { for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i][1] <= off) return [nodes[i][0], off - nodes[i][1]]; };
    const r = document.createRange();
    r.setStart(...pos(at)); r.setEnd(...pos(at + phrase.length)); return r;
  };
  const doc = (r) => ({ x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height });
  const lines = (r) => [...r.getClientRects()].map(doc);
`;

async function capture({ send }, strip) {
  const r = await send("Runtime.evaluate", { returnByValue: true, expression: `(() => { ${HELPERS}
    const s = ${JSON.stringify(strip)}; const p = paraOf(s.para);
    if (!p) return { error: 'no block holds: ' + s.para };
    const from = rangeOf(p, s.from), to = rangeOf(p, s.to);
    if (!from || !to) return { error: 'from/to text is not in that block' };
    const marks = (s.marks || []).map(m => { const r = rangeOf(p, m); return r ? lines(r) : null; });
    if (marks.includes(null)) return { error: 'a mark phrase is not in that block' };
    const last = lines(to).at(-1);
    return { block: doc(p.getBoundingClientRect()), top: lines(from)[0].y, bottom: last.y + last.h, marks };
  })()` });
  const info = r.result.value;
  if (!info || info.error) throw new Error(`${strip.name}: ${info ? info.error : JSON.stringify(r.exceptionDetails)}`);
  const clip = { x: info.block.x - PAD_X, y: info.top - PAD_Y, width: info.block.w + PAD_X * 2,
    height: info.bottom - info.top + PAD_Y * 2, scale: 1 };
  const shot = await send("Page.captureScreenshot", { format: "png", clip, captureBeyondViewport: true });
  const file = path.join(spec.out_dir, `${strip.name}.png`);
  fs.writeFileSync(file, Buffer.from(shot.data, "base64"));
  const px = (v) => Math.round(v * scale);
  const highlight = info.marks.flat().filter((b) => b.w > 1)
    .map((b) => [px(b.x - clip.x) - 4, px(b.y - clip.y), px(b.x + b.w - clip.x) + 4, px(b.y + b.h - clip.y)]);
  return { name: strip.name, file, size: [px(clip.width), px(clip.height)], portraitHighlight: highlight };
}

try {
  const cdp = connect((await pageTarget()).webSocketDebuggerUrl);
  await cdp.opened;
  await cdp.send("Page.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: scale, mobile: true });
  const loaded = cdp.once("Page.loadEventFired");
  await cdp.send("Page.navigate", { url: spec.url });
  await loaded;
  await sleep(2500);
  // Help centers hide answers in collapsed sections; a hidden paragraph has no box to measure.
  if (spec.before) {
    await cdp.send("Runtime.evaluate", { expression: spec.before });
    await sleep(800);
  }
  // Cookie bars and sticky headers must never land in a strip.
  await cdp.send("Runtime.evaluate", { expression: `for (const el of document.querySelectorAll('*')) {
    const p = getComputedStyle(el).position; if (p === 'fixed' || p === 'sticky') el.style.display = 'none'; }` });
  for (const strip of spec.strips) console.log(JSON.stringify(await capture(cdp, strip)));
  cdp.ws.close();
} finally {
  const exited = new Promise((r) => chrome.once("exit", r));
  chrome.kill();
  await exited;
  fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
