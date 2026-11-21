import {createContext, useContext} from 'react';
import {spring, interpolate, useCurrentFrame} from 'remotion';
import type {Brand, Job} from './types';
import {FPS, type Time} from './time';
import type {Layout} from './layout';

export type Ctx = {job: Job; time: Time; brand: Brand; L: Layout};
export const JobCtx = createContext<Ctx | null>(null);

export const useJob = () => {
  const c = useContext(JobCtx);
  if (!c) throw new Error('JobCtx missing');
  return c;
};

// Animation helpers bound to the job timeline. `at` is always source seconds.
export const useAnim = () => {
  const frame = useCurrentFrame();
  const {time} = useJob();
  const pop = (at: number, damping = 18) => spring({frame: frame - time.f(at), fps: FPS, config: {damping, mass: 0.7}});
  const windowFade = (from: number, to: number, d = 8) =>
    interpolate(frame, [time.f(from), time.f(from) + d, time.f(to) - d, time.f(to)], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return {frame, pop, windowFade, f: time.f};
};
