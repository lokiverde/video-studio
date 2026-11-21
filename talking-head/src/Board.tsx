import {interpolate} from 'remotion';
import {useAnim, useJob} from './ctx';
import {THEMES, canvasCss, display, type Theme} from './studio/theme';
import {nextGraphicStart} from './boardSpans';
import {FPS} from './time';
import {isSplit} from './split/geom';
import type {Board as BoardT} from './types';

const FADE_F = 7;

export type Show = BoardT['shows'][number];

// Sizes for one board layout: a row of tall cards (16:9 full screen) or a stack of rows
// (9:16 full screen, and the split card in both aspects)
export type BoardDims = {
  rows: boolean;
  cardW: number;
  cardH: number;
  gap: number;
  titleTop: number;
  titleFont: number;
  padTop: number;
  pad: string;
  tagFont: number;
  labelFont: number;
  qFont: number;
  subFont: number;
  litScale: number;
};

export const fullDims = (portrait: boolean, W: number, n: number): BoardDims =>
  portrait
    ? {rows: true, cardW: 860, cardH: Math.min(230, (1300 - (n - 1) * 22) / n), gap: 22, titleTop: 250, titleFont: 40, padTop: 140, pad: '24px 36px', tagFont: 64, labelFont: 54, qFont: 110, subFont: 34, litScale: 1.06}
    : {rows: false, cardW: Math.min(340, (W - 160 - (n - 1) * 26) / n), cardH: 440, gap: 26, titleTop: 150, titleFont: 36, padTop: 40, pad: '34px 30px', tagFont: 58, labelFont: 52, qFont: 110, subFont: 32, litScale: 1.06};

// The title and the cards. Earlier cards dim once the active one lights up; cards past
// `revealed` stay "?" so #1 is a secret until its show.
export const BoardBody = ({b, show, t, d}: {b: BoardT; show: Show; t: Theme; d: BoardDims}) => {
  const {pop} = useAnim();
  const lit = pop(show.from + 0.45, 14);
  const rest = t.dark ? 'rgba(255,255,255,.10)' : 'rgba(0,0,0,.08)';
  return (
    <>
      {b.title && (
        <div style={{position: 'absolute', left: 0, right: 0, top: d.titleTop, textAlign: 'center', fontFamily: display, fontWeight: 700, fontSize: d.titleFont, letterSpacing: 6, color: t.accent, textTransform: 'uppercase'}}>{b.title}</div>
      )}
      <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: d.rows ? 'column' : 'row', alignItems: 'center', justifyContent: 'center', gap: d.gap, paddingTop: d.padTop}}>
        {b.items.map((item, i) => {
          const shown = i < show.revealed;
          const active = i === show.active;
          const kin = pop(show.from + 0.06 * i, 16);
          const glow = active ? lit : 0;
          return (
            <div
              key={i}
              style={{
                width: d.cardW,
                height: d.cardH,
                borderRadius: d.rows && !t.dark ? 20 : 26,
                boxSizing: 'border-box',
                padding: d.pad,
                display: 'flex',
                flexDirection: d.rows ? 'row' : 'column',
                alignItems: d.rows ? 'center' : 'flex-start',
                justifyContent: d.rows ? 'flex-start' : 'space-between',
                gap: d.rows ? 34 : 0,
                background: t.dark ? `rgba(255,255,255,${0.04 + 0.05 * glow})` : '#fff',
                border: `2px solid ${glow > 0.05 ? t.accent : rest}`,
                boxShadow: glow > 0.05 ? (t.dark ? `0 0 ${60 * glow}px ${t.accent}66, inset 0 0 ${40 * glow}px ${t.accent}22` : `0 ${14 * glow}px ${40 * glow}px ${t.accent}38`) : 'none',
                // a teaser show (active -1) lights nothing and dims nothing
                opacity: kin * (active || show.active < 0 ? 1 : interpolate(lit, [0, 1], [1, 0.5])),
                transform: `translateY(${(1 - kin) * 40}px) scale(${1 + (d.litScale - 1) * glow})`,
              }}
            >
              <div style={{fontFamily: display, fontWeight: 800, fontSize: d.tagFont, color: active ? t.accent : t.mute, letterSpacing: -1, minWidth: d.rows && !t.dark ? d.tagFont * 1.5 : undefined}}>{item.tag ?? `${i + 1}`}</div>
              <div>
                <div style={{fontFamily: display, fontWeight: 700, fontSize: shown ? d.labelFont : d.qFont, lineHeight: 1.05, color: t.ink, letterSpacing: -1}}>{shown ? item.label : '?'}</div>
                {shown && item.sub && <div style={{fontFamily: display, fontSize: d.subFont, color: t.mute, marginTop: 10}}>{item.sub}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
};

// Board style: the recurring map of the whole video. It slides in at each new item, the
// cards pop in left to right, and the active one lights up a beat later. The split layout
// draws it inside its card instead (split/SplitStage.tsx).
export const Board = () => {
  const {job, L} = useJob();
  const {frame, f, windowFade} = useAnim();
  const b = job.board;
  if (!b || isSplit(job)) return null;
  // a show holds until the next graphic starts and crossfades into it
  const until = (s: {to: number}) => {
    const next = nextGraphicStart(job, s.to);
    return next !== null ? next + FADE_F / FPS : s.to;
  };
  const show = b.shows.find((s) => frame >= f(s.from) - 2 && frame < f(until(s)) + 2);
  if (!show) return null;
  const t = THEMES.glow;
  const k = windowFade(show.from, until(show), FADE_F);
  return (
    <div style={{position: 'absolute', inset: 0, background: canvasCss(t), opacity: k}}>
      <BoardBody b={b} show={show} t={t} d={fullDims(L.portrait, L.W, b.items.length)} />
    </div>
  );
};
