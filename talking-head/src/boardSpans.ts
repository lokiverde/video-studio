import type {Job} from './types';

// Board style: back-to-back full-screen graphics (sections and board shows) read as one
// continuous stretch, so Tony never flashes in for a few frames in the gap between two.
export const SPAN_GAP_S = 0.8;

export const boardSpans = (job: Job): Array<[number, number]> => {
  const raw = [
    ...job.sections.map((s): [number, number] => [s.evidence[0], s.evidence[1]]),
    ...(job.board?.shows ?? []).map((s): [number, number] => [s.from, s.to]),
  ].sort((a, b) => a[0] - b[0]);
  return raw.reduce<Array<[number, number]>>((spans, [from, to]) => {
    const last = spans[spans.length - 1];
    if (last && from - last[1] <= SPAN_GAP_S) return [...spans.slice(0, -1), [last[0], Math.max(last[1], to)]];
    return [...spans, [from, to]];
  }, []);
};

// The next graphic that starts within the gap after `end`, or null. A board graphic holds
// until then and crossfades into it, so a handoff never shows an empty canvas.
export const nextGraphicStart = (job: Job, end: number): number | null => {
  const starts = [...job.sections.map((s) => s.evidence[0]), ...(job.board?.shows ?? []).map((s) => s.from)].filter(
    (t) => t >= end - 0.05 && t - end <= SPAN_GAP_S,
  );
  return starts.length ? Math.min(...starts) : null;
};
