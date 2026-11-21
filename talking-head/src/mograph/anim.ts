import {useEffect, useState} from 'react';
import {Easing, cancelRender, continueRender, delayRender, interpolate, spring, staticFile} from 'remotion';

// Anton comes from assets/fonts (mograph.py passes it as the public dir). Loaded once per
// tab and only by the Mograph composition, so the talking-head comps never wait on it.
export const ANTON = 'Anton';
let antonReady = false;
let antonLoad: Promise<void> | null = null;

export const useAnton = (): boolean => {
  const [ready, setReady] = useState(antonReady);
  const [handle] = useState(() => (antonReady ? null : delayRender('Loading Anton')));
  useEffect(() => {
    if (ready) return;
    antonLoad ??= new FontFace(ANTON, `url('${staticFile('Anton-Regular.ttf')}') format('truetype')`).load().then((face) => {
      document.fonts.add(face);
      antonReady = true;
    });
    antonLoad.then(() => setReady(true)).catch((err: unknown) => cancelRender(err));
  }, [ready]);
  useEffect(() => {
    if (ready && handle !== null) continueRender(handle);
  }, [ready, handle]);
  return ready;
};

// Width of a line of text in px, measured on a canvas once the font is in.
let canvas: HTMLCanvasElement | null = null;
export const measure = (text: string, font: string): number => {
  canvas ??= document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return text.length * 0.6 * parseFloat(font);
  ctx.font = font;
  return ctx.measureText(text).width;
};

// A spring that starts at `at` seconds: 0 before, settling to 1 after.
export const springAt = (frame: number, fps: number, at: number, damping = 16, mass = 0.7, stiffness = 120): number =>
  spring({frame: frame - Math.round(at * fps), fps, config: {damping, mass, stiffness}});

// 0..1 over [at, at + seconds], eased out.
export const easeAt = (frame: number, fps: number, at: number, seconds: number, ease = Easing.out(Easing.cubic)): number =>
  interpolate(frame, [at * fps, (at + seconds) * fps], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease});

// '#rrggbb' + alpha 0..1 -> '#rrggbbaa'
export const alpha = (hex: string, a: number): string =>
  `${hex}${Math.round(Math.max(0, Math.min(1, a)) * 255).toString(16).padStart(2, '0')}`;

export const formatNumber = (value: number, decimals: number, prefix: string, suffix: string): string =>
  `${prefix}${value.toLocaleString('en-US', {minimumFractionDigits: decimals, maximumFractionDigits: decimals})}${suffix}`;

// Word as mograph.py's _word() normalises it, so `em` matches regardless of case and punctuation.
export const plainWord = (word: string): string => word.toLowerCase().replace(/[^a-z0-9&']/g, '');

// Largest size from `base` down to `floor` at which every text fits `width`, measured with
// font(size). Below the floor the caller wraps instead of shrinking further.
export const fitSize = (texts: string[], font: (size: number) => string, base: number, width: number, floor: number): number => {
  for (let size = base; size > floor; size -= 2) {
    if (texts.every((t) => measure(t, font(size)) <= width)) return size;
  }
  return floor;
};

// Lines a text wraps into at `width` (greedy on spaces, as the browser wraps it).
export const wrapCount = (text: string, font: string, width: number): number => {
  const space = measure(' ', font);
  let lines = 1;
  let used = 0;
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const w = measure(word, font);
    if (used > 0 && used + space + w > width) {
      lines += 1;
      used = w;
    } else {
      used += (used > 0 ? space : 0) + w;
    }
  }
  return lines;
};

// Largest size from `base` down to `floor` at which every text wraps into `maxLines` or
// fewer, or null when none does.
export const fitLines = (texts: string[], font: (size: number) => string, base: number, width: number, floor: number, maxLines: number): number | null => {
  for (let size = base; size >= floor; size -= 2) {
    if (texts.every((t) => !t || wrapCount(t, font(size), width) <= maxLines)) return size;
  }
  return null;
};
