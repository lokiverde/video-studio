import {Easing, useCurrentFrame} from 'remotion';
import {display} from '../studio/theme';
import {ANTON, alpha, easeAt, fitSize, formatNumber, measure, springAt} from './anim';
import {Title, bodyFont, titleLayout} from './Title';
import {boxFor, type CompareProps} from './types';

// Stat compare: one bar per item, each growing from zero at its `at` while its number
// counts up riding the tip of the bar. The highlighted item (the biggest by default) is
// the accent color with a glow and gets a small pop once it lands.

const GROW_S = 1.0;
const GROW = Easing.bezier(0.16, 1, 0.3, 1);
const GAP = 28;

export const Compare = (p: CompareProps) => {
  const frame = useCurrentFrame();
  const {portrait, fps, palette, items} = p;
  const box = boxFor(portrait);
  const title = titleLayout(p.title, portrait, box.w);
  const sourceH = p.source ? 56 : 0;
  const area = box.h - title.height - sourceH;
  const rowH = Math.min(portrait ? 250 : 170, area / items.length);
  const labelSize = fitSize(items.map((it) => it.label), bodyFont(600), rowH * 0.27, box.w, rowH * 0.27 * 0.6);
  const barH = rowH * 0.34;
  const valueSize = rowH * 0.42;
  const finals = items.map((it) => it.text || formatNumber(it.value, p.decimals, p.prefix, p.suffix));
  const widest = Math.max(...finals.map((t) => measure(t, `${valueSize}px ${ANTON}`)));
  const barMax = box.w - widest - GAP * 1.5;
  const top = Math.max(...items.map((it) => it.value), 1e-9);
  const lastAt = Math.max(...items.map((it) => it.at));
  const titleIn = springAt(frame, fps, 0.05);
  // the source fades in as the last bar settles, and always before the scene ends
  const sourceIn = easeAt(frame, fps, Math.min(lastAt + GROW_S * 0.6, p.frames / fps - 0.7), 0.4);
  return (
    <div style={{position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h}}>
      <Title text={p.title} layout={title} palette={palette} appear={titleIn} />
      <div style={{position: 'absolute', top: title.height, left: 0, width: box.w, height: area, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
        {items.map((it, i) => {
          const enter = springAt(frame, fps, it.at - 0.2);
          const grow = easeAt(frame, fps, it.at, GROW_S, GROW);
          const hot = i === p.highlight;
          const width = Math.max(barH, (barMax * it.value) / top) * grow;
          const bump = hot ? easeAt(frame, fps, it.at + GROW_S - 0.05, 0.15) - easeAt(frame, fps, it.at + GROW_S + 0.1, 0.3) : 0;
          const shown = it.text || formatNumber(it.value * grow, p.decimals, p.prefix, p.suffix);
          return (
            <div key={i} style={{height: rowH, opacity: Math.min(1, enter * 1.4), transform: `translateY(${(1 - enter) * 24}px)`}}>
              <div style={{fontFamily: display, fontWeight: 600, fontSize: labelSize, color: alpha(palette.text, hot ? 1 : 0.8), marginBottom: rowH * 0.06, whiteSpace: 'nowrap'}}>{it.label}</div>
              <div style={{position: 'relative', height: barH}}>
                <div style={{position: 'absolute', left: 0, top: 0, width: barMax, height: barH, borderRadius: barH / 2, background: alpha(palette.text, 0.06)}} />
                <div
                  style={{
                    position: 'absolute',
                    left: 0,
                    top: 0,
                    width,
                    height: barH,
                    borderRadius: barH / 2,
                    background: hot ? `linear-gradient(90deg, ${palette.accent}, ${palette.accent_hi})` : palette.dim,
                    boxShadow: hot ? `0 0 ${barH}px ${alpha(palette.accent, 0.45)}` : 'none',
                  }}
                />
                <div
                  style={{
                    position: 'absolute',
                    left: width + GAP,
                    top: barH / 2,
                    transform: `translateY(-50%) scale(${1 + 0.12 * bump})`,
                    transformOrigin: 'left center',
                    fontFamily: ANTON,
                    fontSize: valueSize,
                    lineHeight: 1,
                    color: hot ? palette.text : alpha(palette.text, 0.75),
                    opacity: it.text ? grow : Math.min(1, grow * 4),
                    whiteSpace: 'nowrap',
                  }}
                >
                  {shown}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {p.source && (
        <div style={{position: 'absolute', left: 0, bottom: 0, fontFamily: display, fontSize: portrait ? 30 : 26, color: alpha(palette.text, 0.55), opacity: sourceIn, letterSpacing: 0.5}}>{p.source}</div>
      )}
    </div>
  );
};
