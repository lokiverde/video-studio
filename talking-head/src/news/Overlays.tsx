import {Img, staticFile, interpolate} from 'remotion';
import {useAnim, useJob} from '../ctx';
import {FPS} from '../time';
import {display} from '../studio/theme';
import {TYPED_COLORS, revealed, runsOf, typedCount} from './typing';
import type {Sticker} from '../types';

const SHADOW = '0 3px 18px rgba(0,0,0,.85), 0 0 2px rgba(0,0,0,.9)';

// News style: a line types itself in over Tony (or over a cutaway), key words in color
export const Typed = () => {
  const {job, L} = useJob();
  const {frame, f, windowFade} = useAnim();
  return (
    <>
      {(job.typed ?? []).map((line) => {
        if (frame < f(line.from) || frame >= f(line.to)) return null;
        const k = windowFade(line.from, line.to, 5);
        const count = typedCount(line.text.length, line.to - line.from, (frame - f(line.from)) / FPS);
        const typing = count < line.text.length;
        const big = line.size === 'big';
        const right = line.pos === 'right' && !L.portrait;
        const pad = L.portrait ? 60 : 70;
        const font = big ? (L.portrait ? 120 : 150) : L.portrait ? 56 : 58;
        const scrim = `radial-gradient(ellipse at ${right ? '100%' : '0%'} 0%, rgba(0,0,0,.78) 0%, rgba(0,0,0,.45) 40%, rgba(0,0,0,0) 72%)`;
        return (
          <div key={line.from} style={{position: 'absolute', inset: 0, opacity: k}}>
            <div style={{position: 'absolute', top: 0, [right ? 'right' : 'left']: 0, width: L.portrait ? '100%' : '75%', height: L.portrait ? 820 : 620, background: scrim}} />
            <div style={{position: 'absolute', top: L.portrait ? 250 : 56, left: pad, right: pad, textAlign: right ? 'right' : 'left'}}>
              <span style={{display: 'inline-block', maxWidth: L.portrait ? 960 : big ? 1500 : 1080, fontFamily: display, fontWeight: big ? 800 : 700, fontSize: font, lineHeight: big ? 1.0 : 1.22, letterSpacing: big ? -3 : -0.5, color: '#fff', textShadow: SHADOW, WebkitTextStroke: `${big ? 10 : 6}px rgba(0,0,0,.6)`, paintOrder: 'stroke fill', whiteSpace: 'pre-line'}}>
                {revealed(runsOf(line.text, line.hl), count).map((run, i) => (
                  <span key={i} style={{color: run.color ? TYPED_COLORS[run.color] : undefined}}>
                    {run.text}
                  </span>
                ))}
                {typing && <span style={{display: 'inline-block', width: Math.max(3, font * 0.06), height: font * 0.9, background: '#fff', marginLeft: 4, verticalAlign: 'text-bottom'}} />}
              </span>
            </div>
          </div>
        );
      })}
    </>
  );
};

const stickerBox = (pos: NonNullable<Sticker['pos']>, size: number, portrait: boolean): React.CSSProperties => {
  if (portrait) return {[pos.endsWith('right') ? 'right' : 'left']: 50, top: 1000, width: size, height: size};
  const side = pos.endsWith('right') ? {right: 90} : {left: 90};
  return {...side, ...(pos.startsWith('bottom') ? {bottom: 80} : {top: 320}), width: size, height: size};
};

// News style: a cutout (seal, gavel, stamp, logo) pops in beside Tony's face
export const Stickers = () => {
  const {job, L} = useJob();
  const {pop, windowFade} = useAnim();
  return (
    <>
      {(job.stickers ?? []).map((s) => {
        const k = pop(s.from, 11) * windowFade(s.from, s.to, 5);
        if (k <= 0.001) return null;
        const size = (L.portrait ? 340 : 430) * (s.scale ?? 1);
        const tilt = interpolate(k, [0, 1], [-8, 0]);
        return (
          <div key={s.file + s.from} style={{position: 'absolute', ...stickerBox(s.pos ?? 'left', size, L.portrait), opacity: Math.min(1, k * 1.4), transform: `scale(${0.6 + 0.4 * k}) rotate(${tilt}deg)`}}>
            <Img src={staticFile(s.file)} style={{width: '100%', height: '100%', objectFit: 'contain', filter: 'drop-shadow(0 14px 30px rgba(0,0,0,.55))'}} />
          </div>
        );
      })}
    </>
  );
};
