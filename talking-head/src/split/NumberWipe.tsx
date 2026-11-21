import {Easing} from 'remotion';
import {useAnim, useJob} from '../ctx';
import {display} from '../studio/theme';
import {SPLIT_ACCENT, SPLIT_LIGHT, isSplit} from './geom';

// Split layout: before each numbered item a huge extruded number sweeps across the frame
// (the "5" in the reference), its echoes trailing behind it. It starts a beat before the
// show so it covers the card sliding in. th_lib.WIPE_SHEET_S samples it mid-frame.
// exported for the army style's wipe, which sweeps a drawn number along the same path
export const WIPE_LEAD_S = 0.35;
export const WIPE_F = 40;
export const TRAIL = 16;
export const LAG_F = 1;
// Echoes fade from Brokerage light blue toward the card's off-white
const TRAIL_NEAR = '#4cc3f2';
const TRAIL_FAR = '#eef8fd';
const OUTLINE_PX = 12;

// Path progress: fast in from the bottom left, a slow drift through the middle, fast out
export const travel = (k: number) => {
  if (k < 0.4) return 0.5 * Easing.out(Easing.cubic)(k / 0.4);
  if (k < 0.62) return 0.5 + 0.05 * ((k - 0.4) / 0.22);
  return 0.55 + 0.45 * Easing.in(Easing.cubic)((k - 0.62) / 0.38);
};

const hexMix = (a: string, b: string, k: number) => {
  const ch = (h: string, i: number) => parseInt(h.slice(1 + i * 2, 3 + i * 2), 16);
  const c = [0, 1, 2].map((i) => Math.round(ch(a, i) + (ch(b, i) - ch(a, i)) * k));
  return `rgb(${c.join(',')})`;
};

type Pt = {x: number; y: number};
const lerp = (p: Pt, q: Pt, k: number): Pt => ({x: p.x + (q.x - p.x) * k, y: p.y + (q.y - p.y) * k});

// Offset from the frame centre at path progress u (0..1): in from the bottom left, out top right
export const wipeAt = (W: number, H: number) => {
  const S = {x: -W * 0.75, y: H * 0.55};
  const C = {x: -W * 0.06, y: 0};
  const E = {x: W * 0.95, y: -H * 0.2};
  return (u: number): Pt => (u < 0.5 ? lerp(S, C, u / 0.5) : lerp(C, E, (u - 0.5) / 0.5));
};

export const NumberWipe = () => {
  const {job, L} = useJob();
  const {frame, f} = useAnim();
  const b = job.board;
  if (!b || !isSplit(job) || b.wipe === false) return null;
  const startOf = (from: number) => f(from - WIPE_LEAD_S);
  const show = b.shows.find((s) => s.active >= 0 && frame >= startOf(s.from) && frame < startOf(s.from) + WIPE_F + TRAIL * LAG_F);
  if (!show) return null;
  const t0 = startOf(show.from);
  const digit = (b.items[show.active]?.tag ?? `${b.items.length - show.active}`).replace(/^#/, '');
  const {W, H, portrait} = L;
  const at = wipeAt(W, H);
  // back to front: the farthest echo first, the solid number on top
  const layers = Array.from({length: TRAIL + 1}, (_, i) => TRAIL - i);
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none'}}>
      {layers.map((i) => {
        const k = (frame - t0 - i * LAG_F) / WIPE_F;
        if (k <= 0 || k >= 1) return null;
        const pos = at(travel(k));
        const front = i === 0;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: W / 2 + pos.x,
              top: H / 2 + pos.y,
              transform: 'translate(-50%, -50%) skewX(-6deg)',
              fontFamily: display,
              fontWeight: 900,
              fontSize: portrait ? 1050 : 980,
              lineHeight: 1,
              letterSpacing: -20,
              color: front ? SPLIT_ACCENT : hexMix(TRAIL_NEAR, TRAIL_FAR, i / TRAIL),
              textShadow: front ? '0 18px 50px rgba(0,0,0,.25)' : 'none',
              WebkitTextStroke: front ? `${OUTLINE_PX}px ${SPLIT_LIGHT}` : '3px rgba(255,255,255,.55)',
              paintOrder: 'stroke fill',
            }}
          >
            {digit}
          </div>
        );
      })}
    </div>
  );
};
