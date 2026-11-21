import {useMemo} from 'react';
import {useCurrentFrame} from 'remotion';
import {display} from '../studio/theme';
import {ANTON, alpha, easeAt, measure, plainWord, springAt} from './anim';
import {boxFor, type PunchProps} from './types';

// Kinetic punch line: the words slam in one after another in Anton, the `em` words in the
// accent color with an underline that sweeps under them, a small kick when the last word
// lands, then the sub line rises in below.

const STAGGER = 0.12;
const LINE = 1.02;
const MIN_SIZE = 64;

// Biggest Anton size at which the words wrap into the box (greedy, measured).
const fit = (words: string[], width: number, height: number, maxSize: number, maxLines: number): {size: number; lines: string[][]} => {
  for (let size = maxSize; size >= MIN_SIZE; size -= 4) {
    const font = `${size}px ${ANTON}`;
    const space = measure(' ', font);
    const lines: string[][] = [[]];
    let used = 0;
    for (const word of words) {
      const w = measure(word, font);
      const line = lines[lines.length - 1];
      if (line.length && used + space + w > width) {
        lines.push([word]);
        used = w;
      } else {
        line.push(word);
        used += (line.length > 1 ? space : 0) + w;
      }
    }
    if (lines.length <= maxLines && lines.length * size * LINE <= height) return {size, lines};
  }
  return {size: MIN_SIZE, lines: [words]};
};

export const Punch = ({portrait, fps, palette, text, em, kicker, sub}: PunchProps) => {
  const frame = useCurrentFrame();
  const box = boxFor(portrait);
  const words = useMemo(() => text.trim().toUpperCase().split(/\s+/), [text]);
  const extras = (kicker ? 90 : 0) + (sub ? 150 : 0);
  const {size, lines} = useMemo(
    () => fit(words, box.w, box.h - extras, portrait ? 168 : 176, portrait ? 5 : 3),
    [words, box.w, box.h, extras, portrait],
  );
  const emSet = new Set(em);
  const start = kicker ? 0.35 : 0.15;
  const lastAt = start + (words.length - 1) * STAGGER;
  // a small decaying shake once the last word has slammed down
  const dt = frame / fps - (lastAt + 0.1);
  const shake = dt > 0 ? 7 * Math.exp(-dt * 8) * Math.sin(dt * 60) : 0;
  const kick = easeAt(frame, fps, 0, 0.4);
  const subIn = easeAt(frame, fps, lastAt + 0.45, 0.5);
  // index of each line's first word, so every word keeps its place in the stagger
  const offsets = lines.map((_, li) => lines.slice(0, li).reduce((n, l) => n + l.length, 0));
  return (
    <div style={{position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'}}>
      {kicker && (
        <div style={{display: 'flex', alignItems: 'center', gap: 20, marginBottom: 34, opacity: kick}}>
          <div style={{width: 72 * kick, height: 4, background: palette.accent}} />
          <div style={{fontFamily: display, fontWeight: 600, fontSize: portrait ? 34 : 30, letterSpacing: 6, textTransform: 'uppercase', color: palette.accent_hi}}>{kicker}</div>
          <div style={{width: 72 * kick, height: 4, background: palette.accent}} />
        </div>
      )}
      <div style={{transform: `translate(${shake}px, ${shake * 0.5}px)`}}>
        {lines.map((line, li) => (
          <div key={li} style={{display: 'flex', justifyContent: 'center', gap: size * 0.24, lineHeight: LINE, height: size * LINE}}>
            {line.map((word, wi) => {
              const index = offsets[li] + wi;
              const at = start + index * STAGGER;
              const s = springAt(frame, fps, at, 12, 0.6, 170);
              const accent = emSet.has(plainWord(word));
              const sweep = easeAt(frame, fps, at + 0.18, 0.35);
              return (
                <span
                  key={index}
                  style={{
                    position: 'relative',
                    display: 'inline-block',
                    fontFamily: ANTON,
                    fontSize: size,
                    color: accent ? palette.accent : palette.text,
                    opacity: Math.min(1, s * 1.6),
                    transform: `translateY(${(1 - s) * 0.45 * size}px) scale(${1.3 - 0.3 * s})`,
                    filter: `blur(${Math.max(0, 1 - s) * 12}px)`,
                    textShadow: `0 8px 34px ${alpha(palette.bg_deep, 0.6)}`,
                  }}
                >
                  {word}
                  {accent && (
                    <span style={{position: 'absolute', left: 0, right: 0, bottom: size * 0.02, height: size * 0.07, background: palette.accent_hi, transform: `scaleX(${sweep})`, transformOrigin: 'left center'}} />
                  )}
                </span>
              );
            })}
          </div>
        ))}
      </div>
      {sub && (
        <div style={{marginTop: 40, maxWidth: box.w * 0.86, textAlign: 'center', fontFamily: display, fontWeight: 500, fontSize: portrait ? 48 : 44, lineHeight: 1.25, color: alpha(palette.text, 0.78), opacity: subIn, transform: `translateY(${(1 - subIn) * 22}px)`}}>
          {sub}
        </div>
      )}
    </div>
  );
};
