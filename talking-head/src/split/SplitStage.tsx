import {spring, useCurrentFrame} from 'remotion';
import {useJob} from '../ctx';
import {FPS} from '../time';
import {BlockView} from '../panels/Blocks';
import {ThemeCtx} from '../studio/Blocks';
import {BoardBody, type BoardDims, type Show} from '../Board';
import type {Block, Job, Section} from '../types';
import {SPLIT_ACCENT, SPLIT_LIGHT, SPLIT_THEME, SplitCtx, splitAmount, splitGeom} from './geom';

// One graphic in a run: a section or a board show
type Slide = {from: number; section?: Section; show?: Show};

// Blocks are authored for the board's full-screen column and scaled into the card
const COL_W = 1160;
// Slides sit side by side on one long canvas; the camera pans to each as it starts
const PAN_GAP = 140;
const PAN_SPRING = {damping: 26, stiffness: 190, mass: 0.8};
// The camera moves on as the next graphic's first cue lands, so the new content rides in with
// the pan (never an empty canvas) and the outgoing graphic holds until then
const PAN_LEAD_S = 0.1;
const RAIL_STEP = 120;

const splitDims = (w: number, h: number, n: number): BoardDims => ({
  rows: true,
  cardW: w - 160,
  cardH: Math.min(108, (h - 190 - (n - 1) * 12) / n),
  gap: 12,
  titleTop: 34,
  titleFont: 28,
  padTop: 40,
  pad: '0 40px',
  tagFont: 48,
  labelFont: 46,
  qFont: 62,
  subFont: 28,
  litScale: 1.03,
});

const slidesIn = (job: Job, [lo, hi]: [number, number]): Slide[] =>
  [
    ...job.sections.map((s): Slide => ({from: s.evidence[0], section: s})),
    ...(job.board?.shows ?? []).map((s): Slide => ({from: s.from, show: s})),
  ]
    .filter((s) => s.from >= lo - 1e-6 && s.from <= hi)
    .sort((a, b) => a.from - b.from);

const cueTimes = (b: Block): number[] => [
  ...('at' in b ? [b.at] : []),
  ...('items' in b ? b.items.map((i) => i.at) : []),
  ...('parts' in b ? b.parts.flatMap((p) => (typeof p === 'string' ? [] : [p.at])) : []),
];

const panAt = (s: Slide) => {
  const cues = s.section ? s.section.blocks.flatMap(cueTimes) : [];
  return cues.length ? Math.max(s.from, Math.min(...cues) - PAN_LEAD_S) : s.from;
};

const SlideSection = ({section, scale}: {section: Section; scale: number}) => (
  <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
    <div style={{width: COL_W, flexShrink: 0, transform: `scale(${scale})`, display: 'flex', flexDirection: 'column', gap: 44}}>
      {section.blocks.map((b, i) =>
        b.type === 'receipt' ? (
          <div key={i} style={{display: 'flex', justifyContent: 'center'}}>
            <BlockView block={b} />
          </div>
        ) : (
          <BlockView key={i} block={b} />
        ),
      )}
    </div>
  </div>
);

// A thin track under the canvas, one dot per graphic in the run, sliding with the pan
const Rail = ({n, p, w, h}: {n: number; p: number; w: number; h: number}) => {
  const now = Math.round(p);
  return (
    <div style={{position: 'absolute', left: 0, top: h - 46, width: w, height: 2, background: 'rgba(0,0,0,.08)'}}>
      {Array.from({length: n}, (_, j) => (
        <div
          key={j}
          style={{
            position: 'absolute',
            left: w / 2 + (j - p) * RAIL_STEP - 8,
            top: -7,
            width: 16,
            height: 16,
            borderRadius: 8,
            boxSizing: 'border-box',
            background: j === now ? SPLIT_ACCENT : '#f6f4ec',
            border: `2px solid ${j === now ? SPLIT_LIGHT : 'rgba(0,0,0,.22)'}`,
          }}
        />
      ))}
    </div>
  );
};

// Split layout: the light card that holds every graphic while Tony stays on the right.
// It slides in from the left (from the top in 9:16) as Tony slides over, holds across a
// whole run of graphics, and pans sideways from one graphic to the next.
export const SplitStage = () => {
  const frame = useCurrentFrame();
  const {job, time, L} = useJob();
  const {a, span} = splitAmount(job, time, frame);
  if (a <= 0.002 || !span) return null;
  const {card, inner} = splitGeom(L.portrait);
  const slides = slidesIn(job, span);
  const p = slides.slice(1).reduce((sum, s) => sum + spring({frame: frame - time.f(panAt(s)), fps: FPS, config: PAN_SPRING}), 0);
  const step = inner.w + PAN_GAP;
  const scale = Math.min(1, (inner.w - 120) / COL_W);
  const off = (1 - a) * (L.portrait ? card.y + card.h + 80 : card.x + card.w + 80);
  const b = job.board;
  return (
    <div
      style={{
        position: 'absolute',
        left: card.x,
        top: card.y,
        width: card.w,
        height: card.h,
        borderRadius: card.r,
        background: 'linear-gradient(180deg, #f3f2ee 0%, #ebeae6 100%)',
        boxShadow: '0 30px 80px rgba(20,20,28,.26), 0 0 0 1px rgba(0,0,0,.05)',
        transform: L.portrait ? `translateY(${-off}px)` : `translateX(${-off}px)`,
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: inner.x,
          top: inner.y,
          width: inner.w,
          height: inner.h,
          borderRadius: inner.r,
          overflow: 'hidden',
          background: 'radial-gradient(ellipse at 50% 45%, #fdfcf8 0%, #f7f5ee 65%, #efede5 100%)',
          boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.04)',
        }}
      >
        <ThemeCtx.Provider value={SPLIT_THEME}>
          <SplitCtx.Provider value={{w: inner.w, h: inner.h, scale}}>
            {slides.map((s, j) => {
              const x = (j - p) * step;
              if (Math.abs(x) >= step) return null;
              return (
                <div key={j} style={{position: 'absolute', inset: 0, transform: `translateX(${x}px)`}}>
                  {s.show && b ? <BoardBody b={b} show={s.show} t={SPLIT_THEME} d={splitDims(inner.w, inner.h, b.items.length)} /> : s.section && <SlideSection section={s.section} scale={scale} />}
                </div>
              );
            })}
          </SplitCtx.Provider>
        </ThemeCtx.Provider>
        {slides.length > 1 && <Rail n={slides.length} p={p} w={inner.w} h={inner.h} />}
      </div>
    </div>
  );
};
