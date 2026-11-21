import {display} from '../studio/theme';
import {ANTON, fitSize, measure} from './anim';
import type {Palette} from './types';

// The accent-barred Anton title over a compare or a list. Shrinks to fit the box width,
// and wraps to a second line rather than go below 60% of its size.

const BAR = 12;
const BAR_GAP = 26;
export const TITLE_GAP = 56;   // space between the title and the rows below it

export type TitleLayout = {size: number; lines: number; height: number};

export const titleLayout = (text: string, portrait: boolean, width: number): TitleLayout => {
  if (!text) return {size: 0, lines: 0, height: 0};
  const base = portrait ? 84 : 76;
  const room = width - BAR - BAR_GAP;
  const font = (s: number) => `${s}px ${ANTON}`;
  const size = fitSize([text.toUpperCase()], font, base, room, Math.round(base * 0.6));
  const lines = measure(text.toUpperCase(), font(size)) > room ? 2 : 1;
  return {size, lines, height: lines * size * 1.08 + TITLE_GAP};
};

export const Title = ({text, layout, palette, appear}: {text: string; layout: TitleLayout; palette: Palette; appear: number}) =>
  text ? (
    <div style={{display: 'flex', alignItems: 'stretch', gap: BAR_GAP, opacity: appear, transform: `translateX(${(1 - appear) * -40}px)`}}>
      <div style={{width: BAR, flexShrink: 0, background: palette.accent, transform: `scaleY(${appear})`, margin: `${layout.size * 0.06}px 0`}} />
      <div style={{fontFamily: ANTON, fontSize: layout.size, lineHeight: 1.08, color: palette.text, textTransform: 'uppercase', letterSpacing: 1, whiteSpace: layout.lines > 1 ? 'normal' : 'nowrap', minWidth: 0}}>{text}</div>
    </div>
  ) : null;

export const bodyFont = (weight: number) => (size: number) => `${weight} ${size}px ${display}`;
