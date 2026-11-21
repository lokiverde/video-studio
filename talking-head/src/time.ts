import type {Job} from './types';

export const FPS = 30;

// All cue times in a job are SOURCE seconds. Cuts remove ranges from the source,
// so every cue is mapped through o() to land on the output timeline.
export const makeTime = (job: Pick<Job, 'cuts' | 'srcEnd' | 'endCard'>) => {
  const cuts = [...job.cuts].sort((a, b) => a[0] - b[0]);
  const o = (t: number) => {
    let removed = 0;
    for (const [from, to] of cuts) {
      if (t >= to) removed += to - from;
      else if (t > from) removed += t - from;
    }
    return t - removed;
  };
  const f = (t: number) => Math.round(o(t) * FPS);
  // kept source segments, in order
  const segments: Array<[number, number]> = [];
  let cursor = 0;
  for (const [from, to] of cuts) {
    if (from > cursor) segments.push([cursor, from]);
    cursor = Math.max(cursor, to);
  }
  if (job.srcEnd > cursor) segments.push([cursor, job.srcEnd]);
  const bodyFrames = f(job.srcEnd);
  const endFrames = Math.round((job.endCard?.seconds ?? 0) * FPS);
  return {o, f, segments, bodyFrames, endFrames, totalFrames: bodyFrames + endFrames};
};

export type Time = ReturnType<typeof makeTime>;
