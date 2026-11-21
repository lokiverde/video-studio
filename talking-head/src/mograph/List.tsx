import {useCurrentFrame} from 'remotion';
import {display} from '../studio/theme';
import {ANTON, alpha, easeAt, fitLines, fitSize, measure, springAt} from './anim';
import {Title, bodyFont, titleLayout} from './Title';
import {boxFor, type ListProps} from './types';

// Animated list: each item slides in at its `at` (when the narration names it) with its
// number (or a check) popping in a ring. The newest item is lit in the accent color and
// the earlier ones step back; a rail draws down from badge to badge as the list grows.

const LIT_S = 0.25;
const RESTING = 0.68;   // opacity of an item once a newer one has landed

const Check = ({size, color, draw}: {size: number; color: string; draw: number}) => (
  <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24" style={{display: 'block'}}>
    <path d="M4 12.5 L10 18 L20 6" fill="none" stroke={color} strokeWidth={3.4} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={30} strokeDashoffset={30 * (1 - draw)} />
  </svg>
);

export const List = ({portrait, fps, palette, title, numbered, items}: ListProps) => {
  const frame = useCurrentFrame();
  const box = boxFor(portrait);
  const head = titleLayout(title, portrait, box.w);
  const area = box.h - head.height;
  const rowH = Math.min(portrait ? 220 : 160, area / items.length);
  const badge = rowH * 0.62;
  const hasSub = items.some((it) => it.sub);
  // text stays on one line down to 80% of its size, else takes two lines at the largest
  // size that fits them, so a long item never runs into the next row
  const room = box.w - badge - rowH * 0.3;
  const base = rowH * (hasSub ? 0.32 : 0.36);
  const texts = items.map((it) => it.text);
  const textSize = fitLines(texts, bodyFont(600), base, room, base * 0.8, 1) ?? fitLines(texts, bodyFont(600), base, room, base * 0.5, 2) ?? base * 0.5;
  const subSize = fitSize(items.map((it) => it.sub), bodyFont(400), rowH * 0.22, room, rowH * 0.22 * 0.72);
  const titleIn = springAt(frame, fps, 0.05);
  const blockTop = (area - rowH * items.length) / 2;
  // lit: 1 while an item is the newest, easing down once the next one lands
  const lit = items.map((it, i) => easeAt(frame, fps, it.at, LIT_S) - (i + 1 < items.length ? easeAt(frame, fps, items[i + 1].at, LIT_S) : 0));
  const rail = items.slice(1).reduce((len, it) => len + easeAt(frame, fps, it.at - 0.3, 0.35) * rowH, 0);
  return (
    <div style={{position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h}}>
      <Title text={title} layout={head} palette={palette} appear={titleIn} />
      <div style={{position: 'absolute', top: head.height + blockTop, left: 0, width: box.w}}>
        <div style={{position: 'absolute', left: badge / 2 - 2, top: rowH / 2, width: 4, height: rail, background: alpha(palette.accent, 0.45), borderRadius: 2}} />
        {items.map((it, i) => {
          const enter = springAt(frame, fps, it.at, 15);
          const pop = springAt(frame, fps, it.at, 10, 0.5, 200);
          const on = Math.max(0, Math.min(1, lit[i]));
          const landed = frame >= Math.round(it.at * fps);
          const fade = landed ? RESTING + (1 - RESTING) * on : 0;
          return (
            <div key={i} style={{position: 'relative', height: rowH, display: 'flex', alignItems: 'center', gap: rowH * 0.3, opacity: Math.min(1, enter * 1.5)}}>
              <div style={{position: 'relative', width: badge, height: badge, flexShrink: 0, transform: `scale(${0.3 + 0.7 * pop})`}}>
                <div style={{position: 'absolute', inset: 0, borderRadius: '50%', border: `3px solid ${alpha(palette.accent_hi, 0.7)}`, background: palette.bg}} />
                <div style={{position: 'absolute', inset: 0, borderRadius: '50%', background: palette.accent, opacity: on, boxShadow: `0 0 ${badge * 0.6}px ${alpha(palette.accent, 0.5 * on)}`}} />
                <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: ANTON, fontSize: badge * 0.52, color: on > 0.5 ? palette.bg : palette.text}}>
                  {numbered ? i + 1 : <Check size={badge} color={on > 0.5 ? palette.bg : palette.text} draw={easeAt(frame, fps, it.at + 0.1, 0.3)} />}
                </div>
              </div>
              <div style={{transform: `translateX(${(1 - enter) * -60}px)`, opacity: fade, minWidth: 0}}>
                <div style={{fontFamily: display, fontWeight: 600, fontSize: textSize, lineHeight: 1.1, color: palette.text, whiteSpace: measure(it.text, bodyFont(600)(textSize)) > room ? 'normal' : 'nowrap'}}>{it.text}</div>
                {it.sub && <div style={{fontFamily: display, fontSize: subSize, lineHeight: 1.2, marginTop: rowH * 0.04, color: alpha(palette.accent_hi, 0.9), whiteSpace: measure(it.sub, bodyFont(400)(subSize)) > room ? 'normal' : 'nowrap'}}>{it.sub}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
