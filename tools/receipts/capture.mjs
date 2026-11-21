// Board style receipts: open each quoted comment in headless Chrome, blur the author's name
// and avatar in the page, screenshot just that comment, and measure the quoted line so the
// Receipt block can highlight it. Usage:
//   node capture.mjs <quotes.json> <out-dir> [--only id,id] [--debug]
// quotes.json: [{id, url, text, community, tight?}]. Writes <out-dir>/<id>.png and receipts.json.
import {chromium} from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36';
const VIEW = {width: 1100, height: 1400};
const SCALE = 3;
// tall posts are cropped to a window around the quote (CSS px)
const MAX_CARD_H = 640;
const CROP_MARGIN = 170;
const KEEP_HEADER_WITHIN = 160;
// quotes.json `tight: true`: every word of the comment outside the quote is blurred
// (Fair Housing: schools, crime or who lives somewhere must never be readable on screen)
const TEXT_BLUR = {color: 'transparent', textShadow: '0 0 9px rgba(0,0,0,.55)'};
const BODY_SEL = '#content-text, [id^="post_message_"], .commtext, [data-testid="tweetText"]';
const PAD = 28;
const BLUR = 'blur(9px)';
const CITY_DATA_MAX_PAGES = 30;

// Per platform: the card to screenshot (closest ancestor of the quote) and what to blur in it
const PLATFORMS = {
  YouTube: {
    card: 'ytd-comment-view-model, ytd-comment-renderer',
    // narrow page: YouTube stacks comments under the player and the text wraps bigger
    width: 520,
    blur: ['#author-thumbnail', '#author-text', '#header-author a', '#author-comment-badge'],
    hide: ['#replies', 'ytd-comment-replies-renderer', '#creator-heart', '#linked-comment-badge', '#more', '#less', 'tp-yt-paper-button#more', 'tp-yt-paper-button#less', '.more-button', '.less-button'],
    unclamp: true,
  },
  'Hacker News': {
    // HN text is tiny: a narrow page makes it big relative to the card
    width: 560,
    card: 'table.fatitem, tr.athing',
    blur: ['.hnuser'],
    hide: ['form', 'textarea', '.navs', '.togg'],
  },
  'City-Data': {
    // the page has a minimum width, so the post itself is narrowed and the text rewraps bigger
    width: 820,
    cardWidth: 540,
    card: 'table[id^="post"]',
    blur: ['.bigusername', 'a[href*="/forum/members/"]', 'img[alt*="vatar"]', 'img[src*="avatar"]', 'td.alt2 > div', 'td[id^="td_post_"] ~ td', 'td.alt2'],
    hide: [],
    // lines that carry a member name: the edit stamp goes, a quoted poster's name is blurred
    scrub: [{text: 'Last edited by', action: 'hide'}, {text: 'Originally Posted by', action: 'blur'}],
  },
  X: {
    width: 520,
    card: 'article, [data-testid="tweet"], #app',
    // every profile link: avatar, display name, handle, and the "Replying to @..." names
    blur: ['img[src*="profile_images"]', '[style*="profile_images"]',
      'a[href*="twitter.com/"]:not([href*="/status/"]):not([href*="intent"])',
      'a[href*="x.com/"]:not([href*="/status/"]):not([href*="intent"])'],
    hide: [],
  },
};

const args = process.argv.slice(2);
const [quotesPath, outDir] = args;
const only = (args[args.indexOf('--only') + 1] && args.includes('--only')) ? args[args.indexOf('--only') + 1].split(',') : null;
const debug = args.includes('--debug');
if (!quotesPath || !outDir) {
  console.error('usage: node capture.mjs <quotes.json> <out-dir> [--only id,id] [--debug]');
  process.exit(2);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Runs in the page: find the quote, return the card it lives in and the quote's box
// (fractions of the padded card), after blurring the author.
const markInPage = ({quote, tight, textBlur, bodySel, cardWidth, cardSel, blurSel, hideSel, scrub, unclamp, blur, pad, maxH, margin, keepHeader}) => {
  const normChar = (c) => (/[‘’]/.test(c) ? "'" : /[“”]/.test(c) ? '"' : /\s/.test(c) ? ' ' : c.toLowerCase());
  const flatten = (root) => {
    const chars = [];
    const map = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const s = n.nodeValue;
      for (let i = 0; i < s.length; i++) {
        const c = normChar(s[i]);
        if (c === ' ' && chars[chars.length - 1] === ' ') continue;
        chars.push(c);
        map.push([n, i]);
      }
    }
    return {text: chars.join(''), map};
  };
  const q = quote.split('').map(normChar).join('').replace(/ +/g, ' ').trim();
  const {text, map} = flatten(document.body);
  let start = text.indexOf(q);
  let end = start >= 0 ? start + q.length : -1;
  if (start < 0) {
    const head = q.slice(0, 30);
    const tail = q.slice(-30);
    start = text.indexOf(head);
    const t = start >= 0 ? text.indexOf(tail, start) : -1;
    end = t >= 0 ? t + tail.length : -1;
  }
  if (start < 0 || end < 0) return {error: 'quote not on page'};
  const range = document.createRange();
  range.setStart(map[start][0], map[start][1]);
  range.setEnd(map[end - 1][0], map[end - 1][1] + 1);
  const anchor = range.commonAncestorContainer.nodeType === 1 ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
  const card = anchor.closest(cardSel) || anchor.parentElement;
  for (const sel of hideSel) card.querySelectorAll(sel).forEach((e) => (e.style.display = 'none'));
  // a collapsed comment ("Read more") is clamped by CSS: open every clamp in the card
  if (unclamp) {
    card.querySelectorAll('[collapsed]').forEach((e) => e.removeAttribute('collapsed'));
    const text = anchor.closest('#content-text, #content, ytd-expander') ?? anchor;
    for (let e = text; e && e !== card; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.webkitLineClamp !== 'none') e.style.webkitLineClamp = 'unset';
      if (cs.maxHeight !== 'none') e.style.maxHeight = 'none';
    }
    text.querySelectorAll('*').forEach((e) => {
      if (getComputedStyle(e).webkitLineClamp !== 'none') e.style.webkitLineClamp = 'unset';
    });
  }
  for (const {text: needle, action} of scrub ?? []) {
    const hits = [];
    const sw = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
    for (let n = sw.nextNode(); n; n = sw.nextNode()) if (n.nodeValue.includes(needle) && !range.intersectsNode(n)) hits.push(n);
    for (const n of hits) {
      const block = n.parentElement.closest('div');
      const el = block && !block.contains(anchor) ? block : n.parentElement;
      if (action === 'hide') el.style.display = 'none';
      else el.style.filter = blur;
    }
  }
  for (const sel of blurSel) {
    card.querySelectorAll(sel).forEach((e) => {
      if (e.contains(anchor)) return; // never blur the quote itself
      e.style.filter = blur;
    });
  }
  // @handles in plain text ("Replying to @someone", mentions) get blurred too, never the quote
  const handle = /@[A-Za-z0-9_.-]{2,}/g;
  const texts = [];
  const tw = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
  for (let n = tw.nextNode(); n; n = tw.nextNode()) if (!range.intersectsNode(n) && /@[A-Za-z0-9_]/.test(n.nodeValue)) texts.push(n);
  for (const n of texts) {
    const frag = document.createDocumentFragment();
    let last = 0;
    for (const m of n.nodeValue.matchAll(handle)) {
      frag.append(n.nodeValue.slice(last, m.index));
      const span = document.createElement('span');
      Object.assign(span.style, {filter: blur, display: 'inline-block'});
      span.textContent = m[0];
      frag.append(span);
      last = m.index + m[0].length;
    }
    frag.append(n.nodeValue.slice(last));
    n.replaceWith(frag);
  }
  if (cardWidth) Object.assign(card.style, {width: `${cardWidth}px`, maxWidth: `${cardWidth}px`, tableLayout: 'auto'});
  card.style.padding = `${pad}px`;
  card.style.background = getComputedStyle(card).backgroundColor === 'rgba(0, 0, 0, 0)' ? '#ffffff' : getComputedStyle(card).backgroundColor;
  card.style.boxSizing = 'border-box';
  // measured layout is not changed by this: inline spans, transparent text with a shadow
  function blurOutside(body, range, style) {
    const wrap = (n) => {
      if (!n.nodeValue.trim()) return;
      const span = document.createElement('span');
      Object.assign(span.style, style);
      n.replaceWith(span);
      span.append(n);
    };
    const {startContainer: sNode, startOffset: sOff, endContainer: eNode, endOffset: eOff} = range;
    const nodes = [];
    const w = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) nodes.push(n);
    for (const n of nodes) {
      if (!range.intersectsNode(n)) {
        wrap(n);
        continue;
      }
      // split the end first so the start offset still points into this node
      if (n === eNode && eOff < n.nodeValue.length) wrap(n.splitText(eOff));
      if (n === sNode && sOff > 0) {
        n.splitText(sOff);
        wrap(n);
      }
    }
  }
  anchor.scrollIntoView({block: 'center'});
  const c = card.getBoundingClientRect();
  const rects = [...range.getClientRects()].filter((r) => r.width > 1 && r.height > 1);
  // one box per line: fragments whose tops sit within a few px are the same line
  const lines = [];
  for (const r of rects.sort((a, b) => a.top - b.top || a.left - b.left)) {
    const line = lines.find((l) => Math.abs(l.top - r.top) < 6);
    if (line) Object.assign(line, {left: Math.min(line.left, r.left), right: Math.max(line.right, r.right), bottom: Math.max(line.bottom, r.bottom)});
    else lines.push({top: r.top, left: r.left, right: r.right, bottom: r.bottom});
  }
  const qTop = Math.min(...lines.map((l) => l.top));
  const qBottom = Math.max(...lines.map((l) => l.bottom));
  let top = c.top;
  let bottom = c.bottom;
  if (c.height > maxH) {
    top = qTop - margin - c.top < keepHeader ? c.top : Math.max(c.top, qTop - margin);
    bottom = Math.min(c.bottom, qBottom + margin);
  }
  const clip = {x: c.left, y: top, width: c.width, height: bottom - top};
  const clamp = (v) => Math.round(Math.max(0, Math.min(1, v)) * 1000) / 1000;
  // edges are clamped, not origin and size, so a box never runs past the image
  const box = (l, r, t, b) => {
    const [x0, y0] = [clamp((l - 6 - clip.x) / clip.width), clamp((t - 3 - clip.y) / clip.height)];
    const [x1, y1] = [clamp((r + 6 - clip.x) / clip.width), clamp((b + 3 - clip.y) / clip.height)];
    return [x0, y0, Math.round((x1 - x0) * 1000) / 1000, Math.round((y1 - y0) * 1000) / 1000];
  };
  if (tight) blurOutside(anchor.closest(bodySel) ?? anchor.parentElement, range, textBlur);
  card.setAttribute('data-receipt', '1');
  return {
    clip,
    highlight: box(Math.min(...lines.map((l) => l.left)), Math.max(...lines.map((l) => l.right)), qTop, qBottom),
    lines: lines.map((l) => box(l.left, l.right, l.top, l.bottom)),
    card: `${card.tagName.toLowerCase()}#${card.id}.${[...card.classList].join('.')}`,
  };
};

// Nothing but the card may land in the shot: floating furniture (back-to-top buttons, sticky
// bars) and neighbours that overflow onto it (City-Data's previous post controls).
// Runs right before the shot: some pages add these on scroll.
const hideFloating = () => {
  const card = document.querySelector('[data-receipt="1"]');
  // up to <html>: some widgets hang off <html> itself, outside <body>
  for (let n = card; n && n.parentElement && n !== document.documentElement; n = n.parentElement) {
    for (const sib of n.parentElement.children) if (sib !== n) sib.style.setProperty('visibility', 'hidden', 'important');
  }
  document.querySelectorAll('html *').forEach((e) => {
    const pos = getComputedStyle(e).position;
    // !important: some sites force their sticky bars visible from the stylesheet
    if ((pos === 'fixed' || pos === 'sticky') && !(card && e.contains(card))) e.style.setProperty('display', 'none', 'important');
  });
};

const expandYouTube = async (page) => {
  for (let i = 0; i < 12; i++) {
    if (await page.locator('ytd-comment-thread-renderer').count()) break;
    await page.mouse.wheel(0, 900);
    await sleep(900);
  }
  await sleep(1500);
  // the linked (lc=) comment is pinned first; open any "Read more" so the full text is there
  const more = page.locator('ytd-comment-thread-renderer >> text=/^Read more$/');
  const n = Math.min(await more.count(), 4);
  for (let i = 0; i < n; i++) await more.nth(i).click({timeout: 1500}).catch(() => {});
};

const cityDataPages = (url) => {
  const base = url.replace(/\.html$/, '');
  return [url, ...Array.from({length: CITY_DATA_MAX_PAGES - 1}, (_, i) => `${base}-${i + 2}.html`)];
};

const xEmbed = (url) => {
  const id = url.match(/status\/(\d+)/)?.[1];
  return `https://platform.twitter.com/embed/Tweet.html?id=${id}&theme=light&dnt=true&hideThread=true`;
};

const captureOne = async (ctx, q) => {
  const plat = PLATFORMS[q.community];
  if (!plat) return {error: `no platform rules for ${q.community}`};
  const page = await ctx.newPage();
  await page.setViewportSize({width: plat.width, height: VIEW.height});
  try {
    const urls = q.community === 'City-Data' ? cityDataPages(q.url) : [q.community === 'X' ? xEmbed(q.url) : q.url];
    for (const url of urls) {
      const resp = await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 45000}).catch((e) => ({error: e}));
      if (!resp || resp.error || (resp.status && resp.status() >= 400)) {
        if (q.community === 'City-Data' && url !== urls[0]) return {error: `quote not found in ${urls.indexOf(url)} pages`};
        return {error: `load failed ${url}: ${resp?.error?.message ?? resp?.status?.()}`};
      }
      if (q.community === 'YouTube') await expandYouTube(page);
      else await sleep(q.community === 'X' ? 3500 : 1200);
      const found = await page.evaluate(markInPage, {quote: q.text, tight: !!q.tight, textBlur: TEXT_BLUR, bodySel: BODY_SEL, cardWidth: plat.cardWidth, cardSel: plat.card, blurSel: plat.blur, hideSel: plat.hide, scrub: plat.scrub, unclamp: plat.unclamp, blur: BLUR, pad: PAD, maxH: MAX_CARD_H, margin: CROP_MARGIN, keepHeader: KEEP_HEADER_WITHIN});
      if (found.error && q.community === 'City-Data') continue;
      if (found.error) return found;
      await sleep(400);
      await page.evaluate(hideFloating);
      const file = path.join(outDir, `${q.id}.png`);
      await page.screenshot({path: file, clip: found.clip});
      if (debug) console.error(q.id, url, found.card, JSON.stringify(found.clip));
      const {clip, ...kept} = found;
      return {...kept, file: path.basename(file), page: url};
    }
    return {error: 'quote not found'};
  } finally {
    await page.close();
  }
};

const main = async () => {
  const quotes = JSON.parse(fs.readFileSync(quotesPath, 'utf8')).filter((q) => !only || only.includes(q.id));
  fs.mkdirSync(outDir, {recursive: true});
  const browser = await chromium.launch({executablePath: CHROME, headless: true});
  const ctx = await browser.newContext({viewport: VIEW, deviceScaleFactor: SCALE, userAgent: UA, locale: 'en-US', colorScheme: 'light'});
  const manifestPath = path.join(outDir, 'receipts.json');
  const manifest = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : {};
  for (const q of quotes) {
    const r = await captureOne(ctx, q).catch((e) => ({error: e.message}));
    manifest[q.id] = {...q, ...r};
    console.log(`${r.error ? 'FAIL' : 'ok  '} ${q.id} ${r.error ?? JSON.stringify(r.highlight)}`);
    fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  }
  await browser.close();
};

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
