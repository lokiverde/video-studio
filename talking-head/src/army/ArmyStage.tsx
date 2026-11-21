import {Img, interpolate, spring, staticFile} from 'remotion';
import {useAnim, useJob} from '../ctx';
import {FPS} from '../time';
import {ARMY_NAVY} from './geom';

const fill = {position: 'absolute' as const, inset: 0, width: '100%', height: '100%'};
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
// the punch line lands a beat after the box starts to shrink
const LINE_DELAY_S = 0.15;

// The navy grain canvas (army_draw.canvas) under everything. Full-frame Tony covers it.
export const ArmyCanvas = () => {
  const {job} = useJob();
  if (!job.army) return null;
  return <Img src={staticFile(job.army.canvas)} style={fill} />;
};

// Each inset's punch line, drawn by army.py on a transparent layer under the box, rises in
export const ArmyLines = () => {
  const {job} = useJob();
  const {frame, f, pop, windowFade} = useAnim();
  return (
    <>
      {(job.army?.beats ?? []).map((b) => {
        if (!b.textFile || frame < f(b.from) || frame >= f(b.to)) return null;
        const k = pop(b.from + LINE_DELAY_S, 15) * windowFade(b.from, b.to, 5);
        return (
          <Img
            key={b.from}
            src={staticFile(b.textFile)}
            style={{...fill, opacity: Math.min(1, k), transform: `translateY(${(1 - k) * 46}px) scale(${0.93 + 0.07 * k})`, transformOrigin: '50% 66%'}}
          />
        );
      })}
    </>
  );
};

// Full-screen Army graphics over Tony, his audio carries on. Hard cut in with a short settle,
// then a slow push. An agenda that follows an agenda holds still, so only its new line lands.
export const ArmyGraphics = () => {
  const {job} = useJob();
  const {frame, f} = useAnim();
  const beats = job.army?.beats ?? [];
  return (
    <>
      {beats.map((b, i) => {
        // split beats have a file too, but they live in the card beside Tony (ArmySplitStage)
        if (b.layout !== 'graphic' || !b.file || frame < f(b.from) || frame >= f(b.to)) return null;
        const prev = beats[i - 1];
        const build = b.kind === 'agenda' && prev?.kind === 'agenda' && f(b.from) - f(prev.to) <= 1;
        const settle = build ? 1 : spring({frame: frame - f(b.from), fps: FPS, config: {damping: 20, stiffness: 220}});
        const push = b.kind === 'agenda' ? 0 : interpolate(frame, [f(b.from), f(b.to)], [0, 0.025], clamp);
        return (
          <div key={b.from} style={{...fill, overflow: 'hidden', background: ARMY_NAVY}}>
            <Img src={staticFile(b.file)} style={{...fill, transform: `scale(${1 + 0.04 * (1 - settle) + push})`}} />
          </div>
        );
      })}
    </>
  );
};
