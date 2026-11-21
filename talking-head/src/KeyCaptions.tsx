import {useAnim, useJob} from './ctx';
import {FPS} from './time';
import {display} from './studio/theme';
import {boardSpans} from './boardSpans';
import {SPLIT_ACCENT, SPLIT_LIGHT, isSplit, splitGeom} from './split/geom';

export const KEY_GOLD = '#f5c542';
/** Key words: gold on the board, Brokerage light blue in the split layout. */
export const keyColor = (split: boolean) => (split ? SPLIT_LIGHT : KEY_GOLD);

// where key-word captions (and board phrases) sit
export const keyCaptionBox = (portrait: boolean): React.CSSProperties =>
  portrait ? {left: 60, right: 60, bottom: 400, textAlign: 'center'} : {left: 110, bottom: 84, maxWidth: 1180, textAlign: 'left'};
export const KEY_FONT = {fontFamily: display, fontWeight: 800, lineHeight: 1.12, letterSpacing: -1, color: '#fff', textShadow: '0 4px 28px rgba(0,0,0,.8), 0 0 2px rgba(0,0,0,.9)'} as const;
export const keyFontSize = (portrait: boolean) => (portrait ? 66 : 64);
const KEY_TEAL = '#2dd4bf';

// Split layout in 9:16: Tony's face fills the lower half, so during graphics the line moves up
// to the seam under the card, on a dark pill so it reads over the light card edge
const SEAM = splitGeom(true).card;
const SEAM_BOX: React.CSSProperties = {left: 60, right: 60, top: SEAM.y + SEAM.h - 44, textAlign: 'center'};
const SEAM_FONT = 56;
// Brokerage blue pill (#1d3557 at 92%) so the light blue key words read on it
const SEAM_PILL: React.CSSProperties = {background: `${SPLIT_ACCENT}eb`, padding: '2px 22px', borderRadius: 16, boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone', lineHeight: 1.32};

const norm = (w: string) => w.toLowerCase().replace(/[^a-z0-9$%]/g, '');

// Indexes of caption words that belong to a keyword phrase ("price out" spans two words)
const keyIndexes = (words: string[], keywords: string[]) => {
  const hits = new Set<number>();
  const flat = words.map(norm);
  for (const k of keywords) {
    const parts = k.split(/\s+/).map(norm).filter(Boolean);
    for (let i = 0; i + parts.length <= flat.length; i++) {
      if (parts.every((p, j) => flat[i + j] === p)) parts.forEach((_, j) => hits.add(i + j));
    }
  }
  return hits;
};

// Board style captions (Peverelli format): big bold sentence case, bottom left in 16:9,
// keywords in gold and figures in teal. They step aside for phrases, the board and, in 16:9,
// full-screen graphics. 9:16 keeps them under the graphics for people watching muted.
export const KeyCaptions = () => {
  const {job, time, L} = useJob();
  const {frame, f} = useAnim();
  if (job.style !== 'board') return null;
  const mode = job.captionMode ?? 'auto';
  if (mode === 'off' || mode === 'phrases') return null;
  if (frame >= time.bodyFrames - 6) return null;
  const t = frame / FPS;
  const cap = (job.captions ?? []).find((c) => t >= c.s && t < c.e);
  if (!cap) return null;
  const within = (from: number, to: number) => frame >= f(from) && frame < f(to);
  if ((job.phrases ?? []).some((p) => within(p.from, p.to))) return null;
  if ((job.board?.shows ?? []).some((s) => within(s.from - 0.2, s.to + 0.2))) return null;
  // a name bar says the same thing as the line, and they would stack
  const bars = job.lowerThird ? ([] as Array<{from: number; to: number}>).concat(job.lowerThird) : [];
  if (bars.some((lt) => within(lt.from - 0.2, lt.to + 0.2))) return null;
  const graphics = boardSpans(job).some(([from, to]) => within(from, to + 0.2));
  if (!L.portrait && graphics) return null;
  const split = isSplit(job);
  const seam = L.portrait && graphics && split;
  const words = cap.t.split(/\s+/).filter(Boolean);
  const keys = keyIndexes(words, job.keywords ?? []);
  return (
    <div style={{position: 'absolute', ...(seam ? SEAM_BOX : keyCaptionBox(L.portrait)), ...KEY_FONT, fontSize: seam ? SEAM_FONT : keyFontSize(L.portrait)}}>
      <span style={seam ? SEAM_PILL : undefined}>
        {words.map((w, i) => (
          <span key={i} style={{color: keys.has(i) ? keyColor(split) : /\d/.test(w) ? (split ? SPLIT_LIGHT : KEY_TEAL) : undefined}}>
            {w}
            {i < words.length - 1 ? ' ' : ''}
          </span>
        ))}
      </span>
    </div>
  );
};
