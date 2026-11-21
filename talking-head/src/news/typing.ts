import type {Typed, TypedColor} from '../types';

export const TYPED_COLORS: Record<TypedColor, string> = {green: '#3ee072', red: '#ff5b4f', amber: '#f2a93b'};

export type Run = {text: string; color?: TypedColor};

// Split a line into plain and highlighted runs, in reading order
export const runsOf = (text: string, hl: Typed['hl'] = []): Run[] => {
  let runs: Run[] = [{text}];
  for (const h of hl) {
    runs = runs.flatMap((run) => {
      const i = run.color ? -1 : run.text.indexOf(h.text);
      if (i < 0) return [run];
      return [{text: run.text.slice(0, i)}, {text: h.text, color: h.color ?? 'green'}, {text: run.text.slice(i + h.text.length)}].filter((r) => r.text);
    });
  }
  return runs;
};

// Keep only the first `count` characters across the runs
export const revealed = (runs: Run[], count: number): Run[] => {
  let left = count;
  return runs.flatMap((run) => {
    if (left <= 0) return [];
    const part = {...run, text: run.text.slice(0, left)};
    left -= run.text.length;
    return [part];
  });
};

const MIN_CPS = 28;
const TYPE_SHARE = 0.45; // a line finishes typing in under half the time it is on screen

export const typedCount = (chars: number, seconds: number, elapsed: number) => {
  const cps = Math.max(MIN_CPS, chars / Math.max(0.3, seconds * TYPE_SHARE));
  return Math.max(0, Math.min(chars, Math.floor(elapsed * cps)));
};
