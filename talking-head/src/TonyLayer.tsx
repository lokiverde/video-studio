import {OffthreadVideo, Sequence, staticFile, useCurrentFrame, spring, interpolate} from 'remotion';
import {useJob} from './ctx';
import {FPS} from './time';
import {mirrorX} from './layout';
import {isStudio, type Job} from './types';
import {boardSpans} from './boardSpans';
import {SPLIT_FOCUS, isSplit, splitAmount, splitGeom} from './split/geom';
import {ARMY_LIGHT, ARMY_NAVY, ARMY_SPLIT_FOCUS, insetAmount, isArmy, splitAmount as armySplitAmount} from './army/geom';

// Source time currently on screen, walking the kept segments
const sourceTime = (frame: number, segments: Array<[number, number]>) => {
  let cursor = 0;
  for (const [from, to] of segments) {
    const dur = Math.round((to - from) * FPS);
    if (frame < cursor + dur) return from + (frame - cursor) / FPS;
    cursor += dur;
  }
  return segments.length ? segments[segments.length - 1][1] : 0;
};

// Studio, news, board and army styles: wide and tight framings alternate at every cut and every extra punch
const punchedAt = (job: Job, t: number) => {
  if (!(isStudio(job) || job.style === 'army') || job.punch === false) return false;
  const marks = new Set([...job.cuts.map(([, end]) => end), ...(job.punches ?? [])]);
  let n = 0;
  marks.forEach((m) => {
    if (m <= t) n += 1;
  });
  return n % 2 === 1;
};

// Tony's footage. Full frame by default, shrinks to a portrait card inside evidence windows.
// Board style hides him behind full-screen graphics; its split layout slides him to the right third.
// Army style moves him into his light-blue framed split panel, or the inset box at the top.
export const TonyLayer = () => {
  const frame = useCurrentFrame();
  const {job, time, brand, L} = useJob();
  const studio = isStudio(job);
  let a = 0;
  let active = job.sections[0];
  for (const s of job.sections) {
    const inS = spring({frame: frame - time.f(s.evidence[0]), fps: FPS, config: {damping: 20}});
    const outS = spring({frame: frame - time.f(s.evidence[1]), fps: FPS, config: {damping: 20}});
    const v = inS - outS;
    if (v > a) {
      a = v;
      active = s;
    }
  }
  const split = isSplit(job);
  const army = isArmy(job);
  // army: how far into the inset box and into the split panel (one rises as the other falls)
  const aIn = army ? insetAmount(job, time, frame) : 0;
  const aSp = army ? armySplitAmount(job, time, frame) : 0;
  if (split) a = splitAmount(job, time, frame).a;
  else if (army) a = aIn + aSp;
  else if (job.style === 'board') {
    // hidden across a whole run of graphics, not section by section
    const springAt = (t: number) => spring({frame: frame - time.f(t), fps: FPS, config: {damping: 20}});
    a = Math.max(0, ...boardSpans(job).map(([from, to]) => springAt(from) - springAt(to)));
  }
  // army keeps the spring's overshoot, so the box lands with a small bounce
  a = army ? Math.max(0, a) : Math.min(1, Math.max(0, a));
  const settled = Math.min(1, a);
  const card = army ? job.army!.inset : split ? splitGeom(L.portrait).tony : studio && !L.portrait && active?.side === 'left' ? mirrorX(L.card, L.W) : L.card;
  const hidden = studio && !split && (active?.full || job.style === 'board') ? a : 0;
  const armyTo = (from: number, inset: number, panel: number) => from + aIn * (inset - from) + aSp * (panel - from);
  const lerp = (k: 'x' | 'y' | 'w' | 'h' | 'r') =>
    army ? armyTo(L.full[k], job.army!.inset[k], job.army!.split.tony[k]) : interpolate(a, [0, 1], [L.full[k], card[k]]);
  const border = army ? job.army!.inset.border * settled : studio ? 0 : 8 * a;
  // army: the rule sits inside the box, like army.py's frames; evidence: outside the card
  const pad = army ? 0 : border;
  const src = staticFile(job.source);
  const CENTER = {x: 0.5, y: 0.5, zoom: 1};
  const fr = job.framing ?? {};
  const fullF = (L.portrait ? fr.portraitFull : fr.full) ?? fr.full ?? CENTER;
  const cardF = split
    ? (L.portrait ? fr.portraitSplit : fr.split) ?? SPLIT_FOCUS[L.portrait ? 'portrait' : 'landscape']
    : army
      ? (L.portrait ? fr.portraitInset : fr.inset) ?? fr.inset ?? fullF
      : (L.portrait ? fr.portraitCard : fr.card) ?? fr.card ?? CENTER;
  const panelF = (L.portrait ? fr.portraitSplit : fr.split) ?? ARMY_SPLIT_FOCUS[L.portrait ? 'portrait' : 'landscape'];
  const mix = (k: 'x' | 'y' | 'zoom') => (army ? armyTo(fullF[k], cardF[k], panelF[k]) : interpolate(a, [0, 1], [fullF[k], cardF[k]]));
  const punch = punchedAt(job, sourceTime(frame, time.segments)) ? 1 + ((job.punchZoom ?? 1.15) - 1) * (1 - settled) : 1;
  const focus = `${mix('x') * 100}% ${mix('y') * 100}%`;
  const style = {width: '100%', height: '100%', objectFit: 'cover' as const, objectPosition: focus, transform: `scale(${mix('zoom') * punch})`, transformOrigin: focus};
  const shadow = army
    ? `0 0 44px 8px rgba(0,173,239,${0.42 * settled})`
    : studio ? `0 30px 70px rgba(0,0,0,${0.35 * a})` : `0 24px 60px rgba(15,42,67,${0.3 * a})`;
  let cursor = 0;
  return (
    <div
      style={{
        position: 'absolute',
        left: lerp('x') - pad,
        top: lerp('y') - pad,
        width: lerp('w') + pad * 2,
        height: lerp('h') + pad * 2,
        borderRadius: lerp('r') + pad,
        border: `${border}px solid ${army ? ARMY_LIGHT : '#fff'}`,
        outline: !studio && !army && a > 0.05 ? `${3 * a}px solid ${brand.navy}` : 'none',
        boxSizing: 'border-box',
        overflow: 'hidden',
        background: army ? ARMY_NAVY : '#fff',
        opacity: 1 - hidden,
        transform: `scale(${1 - hidden * 0.08})`,
        // split: the card casts the shadow onto Tony, not the other way round
        boxShadow: a > 0.05 && !split ? shadow : 'none',
      }}
    >
      <div style={{width: '100%', height: '100%', borderRadius: lerp('r'), overflow: 'hidden'}}>
        {time.segments.map(([from, to], i) => {
          const start = cursor;
          const dur = Math.round((to - from) * FPS);
          cursor += dur;
          return (
            <Sequence key={i} from={start} durationInFrames={dur} layout="none">
              <OffthreadVideo src={src} startFrom={Math.round(from * FPS)} endAt={Math.round(to * FPS)} style={style} />
            </Sequence>
          );
        })}
      </div>
    </div>
  );
};
