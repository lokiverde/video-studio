import {createContext} from 'react';
import {spring} from 'remotion';
import type {Rect} from '../layout';
import type {Frame, Job} from '../types';
import type {Time} from '../time';
import {FPS} from '../time';
import {boardSpans} from '../boardSpans';
import {THEMES} from '../studio/theme';

// Split layout, the quiz tips look (Simon Scrapes "How the Top 1% Use Claude Code
// Differently", reviewed 2026-10-13). Tony never leaves: when graphics come in he slides to
// the right third and punches in, and a light card slides over from the left, overlapping
// his edge a little. Everything outside Tony and the card is the pale backdrop.
export type SplitGeom = {tony: Rect; card: Rect; inner: Rect};

export const SPLIT_LANDSCAPE: SplitGeom = {
  tony: {x: 1290, y: 0, w: 630, h: 1080, r: 0},
  card: {x: 24, y: 44, w: 1400, h: 992, r: 34},
  // the cream canvas inside the card's bezel, relative to the card
  inner: {x: 56, y: 76, w: 1288, h: 840, r: 22},
};

// 9:16: the card on top, Tony below it, both clear of the platform UI at top and bottom
export const SPLIT_PORTRAIT: SplitGeom = {
  tony: {x: 0, y: 1010, w: 1080, h: 910, r: 0},
  card: {x: 24, y: 170, w: 1032, h: 880, r: 34},
  inner: {x: 32, y: 56, w: 968, h: 768, r: 22},
};

export const splitGeom = (portrait: boolean) => (portrait ? SPLIT_PORTRAIT : SPLIT_LANDSCAPE);

// Where Tony's face lands in his strip. 16:9 puts it right of the card's overlap, 9:16 keeps
// it high so the captions sit on his chest. A job overrides with framing.split / portraitSplit.
export const SPLIT_FOCUS: {landscape: Frame; portrait: Frame} = {
  landscape: {x: 0.46, y: 0.4, zoom: 1.12},
  portrait: {x: 0.5, y: 0.6, zoom: 1.3},
};

export const SPLIT_BACKDROP = '#e3e2dd';
// Brokerage brand (Tony, 2026-10-14: "Brokerage blue rather than yellow, with an outline of
// light blue"). Same values as siteone.com: the brand navy and cyan.
export const SPLIT_ACCENT = '#1d3557';
export const SPLIT_LIGHT = '#29a8d6';
/** The light card's theme: the paper look with Brokerage blue as its accent. */
export const SPLIT_THEME = {...THEMES.paper, accent: SPLIT_ACCENT};

// Snappier than the board's fade: the reference hard-cuts, this slides in about 12 frames
const SPLIT_SPRING = {damping: 22, stiffness: 170, mass: 0.8};

export const isSplit = (job: Job) => job.style === 'board' && job.layout === 'split';

// How far into the split we are, 0 (Tony full frame) to 1 (Tony right, card in), and the
// run of graphics it belongs to. Tony and the card share it, so they always move together.
export const splitAmount = (job: Job, time: Time, frame: number) => {
  const at = (t: number) => spring({frame: frame - time.f(t), fps: FPS, config: SPLIT_SPRING});
  let best = {a: 0, span: null as [number, number] | null};
  for (const span of boardSpans(job)) {
    const a = at(span[0]) - at(span[1]);
    if (a > best.a) best = {a, span};
  }
  return {a: Math.min(1, Math.max(0, best.a)), span: best.span};
};

// The inner canvas size, for blocks (receipts) that size themselves to the card
// (scale: how much the block column is shrunk to fit, so a receipt can fill the card anyway)
export const SplitCtx = createContext<{w: number; h: number; scale: number} | null>(null);
