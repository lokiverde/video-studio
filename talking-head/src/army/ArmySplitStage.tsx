import {Img, OffthreadVideo, Sequence, spring, staticFile, useCurrentFrame} from 'remotion';
import {useJob} from '../ctx';
import {FPS} from '../time';
import type {ArmyBeat} from '../types';
import {LAG_F, TRAIL, WIPE_F, WIPE_LEAD_S, travel, wipeAt} from '../split/NumberWipe';
import {ARMY_LIGHT, ARMY_NAVY, splitAmount, splitRunAt} from './geom';

// Graphics in a run sit side by side on one strip; the card pans to each as it cuts in
const PAN_SPRING = {damping: 26, stiffness: 190, mass: 0.8};
const PAN_GAP = 120;
const CARD_RULE = 'inset 0 0 0 3px rgba(0,173,239,.55)';
// a recording keeps playing while the card pans to the next slot (CLIP_TAIL_S in th_army_build)
const CLIP_TAIL_F = Math.round(1.0 * FPS);

type Slot = {from: number; beats: ArmyBeat[]};

// A screen recording in its light-blue framed window on the card. Muted: Tony's audio carries
// on. focus picks the part of the recording to show (0 = left/top edge, 1 = right/bottom).
const ClipWindow = ({beat}: {beat: ArmyBeat}) => {
  const {time} = useJob();
  const win = beat.window!;
  const [fx, fy] = beat.focus ?? [0.5, 0.5];
  const origin = `${fx * 100}% ${fy * 100}%`;
  const from = time.f(beat.from);
  return (
    <div style={{position: 'absolute', left: win.x, top: win.y, width: win.w, height: win.h, borderRadius: win.r, overflow: 'hidden'}}>
      <Sequence from={from} durationInFrames={Math.max(1, time.f(beat.to) - from + CLIP_TAIL_F)} layout="none">
        <div style={{position: 'absolute', inset: 0, transform: `scale(${beat.zoom ?? 1})`, transformOrigin: origin}}>
          <OffthreadVideo
            src={staticFile(beat.clip!)}
            muted
            startFrom={Math.round((beat.start ?? 0) * FPS)}
            playbackRate={beat.rate ?? 1}
            style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: origin}}
          />
        </div>
      </Sequence>
      <div style={{position: 'absolute', inset: 0, borderRadius: win.r, boxShadow: `inset 0 0 0 ${win.border}px ${ARMY_LIGHT}`}} />
    </div>
  );
};

// One slot per graphic, except an agenda that continues the one before: it builds in place
const slotsIn = (beats: ArmyBeat[], [lo, hi]: [number, number]): Slot[] =>
  beats
    .filter((b) => b.layout === 'split' && b.file && b.from >= lo - 1e-6 && b.from < hi)
    .reduce<Slot[]>((slots, b) => {
      const last = slots[slots.length - 1];
      const prev = last?.beats[last.beats.length - 1];
      if (last && b.kind === 'agenda' && prev?.kind === 'agenda' && b.from - prev.to < 0.05) {
        return [...slots.slice(0, -1), {...last, beats: [...last.beats, b]}];
      }
      return [...slots, {from: b.from, beats: [b]}];
    }, []);

// Army split, the main layout: the navy graphics card beside Tony's panel (above it in 9:16).
// It slides in from the left (from the top in 9:16) as Tony moves into his panel, holds across
// the run and pans sideways from one graphic to the next.
export const ArmySplitStage = () => {
  const frame = useCurrentFrame();
  const {job, time, L} = useJob();
  const run = splitRunAt(job, time, frame);
  const a = splitAmount(job, time, frame);
  if (!job.army || !run || a <= 0.002) return null;
  const {card} = job.army.split;
  const slots = slotsIn(job.army.beats, run);
  const p = slots.slice(1).reduce((sum, s) => sum + spring({frame: frame - time.f(s.from), fps: FPS, config: PAN_SPRING}), 0);
  const step = card.w + PAN_GAP;
  const off = (1 - a) * (L.portrait ? card.y + card.h + 80 : card.x + card.w + 80);
  return (
    <div
      style={{
        position: 'absolute',
        left: card.x,
        top: card.y,
        width: card.w,
        height: card.h,
        borderRadius: card.r,
        overflow: 'hidden',
        background: ARMY_NAVY,
        boxShadow: '0 30px 80px rgba(0,8,16,.55)',
        transform: L.portrait ? `translateY(${-off}px)` : `translateX(${-off}px)`,
      }}
    >
      {slots.map((s, j) => {
        const x = (j - p) * step;
        if (Math.abs(x) >= step) return null;
        // an agenda slot shows its newest line; before the first one lands, the first
        const shown = s.beats.filter((b) => frame >= time.f(b.from)).pop() ?? s.beats[0];
        return (
          <div key={s.from} style={{position: 'absolute', left: 0, top: 0, width: card.w, height: card.h, transform: `translateX(${x}px)`}}>
            <Img src={staticFile(shown.file!)} style={{position: 'absolute', inset: 0, width: card.w, height: card.h}} />
            {shown.kind === 'clip' ? <ClipWindow beat={shown} /> : null}
          </div>
        );
      })}
      <div style={{position: 'absolute', inset: 0, borderRadius: card.r, boxShadow: CARD_RULE, pointerEvents: 'none'}} />
    </div>
  );
};

// Before a trading card beside Tony, its number (drawn by th_army_build in the light-blue
// Anton) sweeps across the whole frame with a trail of echoes, like the quiz tips wipe.
export const ArmyWipe = () => {
  const frame = useCurrentFrame();
  const {job, time, L} = useJob();
  const wipe = (job.army?.wipes ?? []).find((w) => {
    const t0 = time.f(w.at - WIPE_LEAD_S);
    return frame >= t0 && frame < t0 + WIPE_F + TRAIL * LAG_F;
  });
  if (!wipe) return null;
  const t0 = time.f(wipe.at - WIPE_LEAD_S);
  const at = wipeAt(L.W, L.H);
  const height = L.portrait ? 1000 : 940;
  // back to front: the farthest echo first, the solid number on top
  const layers = Array.from({length: TRAIL + 1}, (_, i) => TRAIL - i);
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none'}}>
      {layers.map((i) => {
        const k = (frame - t0 - i * LAG_F) / WIPE_F;
        if (k <= 0 || k >= 1) return null;
        const pos = at(travel(k));
        return (
          <Img
            key={i}
            src={staticFile(wipe.file)}
            style={{
              position: 'absolute',
              left: L.W / 2 + pos.x,
              top: L.H / 2 + pos.y,
              height,
              transform: 'translate(-50%, -50%) skewX(-6deg)',
              opacity: i === 0 ? 1 : 0.45 * (1 - i / (TRAIL + 1)),
            }}
          />
        );
      })}
    </div>
  );
};
