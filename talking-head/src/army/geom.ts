import {spring} from 'remotion';
import {FPS, type Time} from '../time';
import type {Frame, Job} from '../types';

// Army style (docs/army.md, "With Tony on camera"): Tony's footage on the Brokerage navy
// grain canvas. The main layout is the split (Tony in his own light-blue framed panel, Army
// graphics in a navy card beside him); full frame, the inset box and full-screen graphics are
// the others. th.py sends the drawn stills, the geometry and the runs Tony holds each place
// (th_army.render_props), so no layout logic is duplicated here.
export const ARMY_NAVY = '#1d3557';
export const ARMY_LIGHT = '#29a8d6';

// A touch of overshoot so the box lands with a little bounce instead of sliding to a stop
const INSET_SPRING = {damping: 16, stiffness: 150, mass: 0.8};
// Same feel as the quiz tips split: snappy, about 12 frames
export const ARMY_SPLIT_SPRING = {damping: 22, stiffness: 170, mass: 0.8};

// Where Tony's face sits in his split panel unless the job sets framing.split / portraitSplit
export const ARMY_SPLIT_FOCUS: {landscape: Frame; portrait: Frame} = {
  landscape: {x: 0.5, y: 0.4, zoom: 1.1},
  portrait: {x: 0.5, y: 0.4, zoom: 1.6},
};

export const isArmy = (job: Job) => job.style === 'army' && !!job.army;

const amount = (runs: Array<[number, number]>, time: Time, frame: number, config: typeof INSET_SPRING) => {
  const at = (t: number) => spring({frame: frame - time.f(t), fps: FPS, config});
  return Math.max(0, ...runs.map(([from, to]) => at(from) - at(to)));
};

// 0 Tony full frame, 1 Tony in the box. Can run a little past 1 while the spring settles.
export const insetAmount = (job: Job, time: Time, frame: number) => amount(job.army?.runs.inset ?? [], time, frame, INSET_SPRING);

// 0 Tony full frame, 1 Tony in his split panel with the graphics card beside him
export const splitAmount = (job: Job, time: Time, frame: number) => Math.min(1, amount(job.army?.runs.split ?? [], time, frame, ARMY_SPLIT_SPRING));

// The split run on screen at this frame: the one playing, else one still sliding out
const SLIDE_OUT_F = 20;
export const splitRunAt = (job: Job, time: Time, frame: number): [number, number] | null => {
  const runs = job.army?.runs.split ?? [];
  const playing = runs.find(([from, to]) => frame >= time.f(from) && frame < time.f(to));
  return playing ?? runs.filter(([, to]) => frame >= time.f(to) && frame < time.f(to) + SLIDE_OUT_F).pop() ?? null;
};

// Captions sit in the band under the punch line (army.py keeps graphics above 74% of the frame)
export const armyCaptionBox = (portrait: boolean): React.CSSProperties =>
  portrait ? {left: 60, right: 60, top: 1452} : {left: 0, width: 1920, bottom: 60};
export const ARMY_CAPTION_BG = 'rgba(0,43,73,.9)';
