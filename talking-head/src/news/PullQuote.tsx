import {useContext} from 'react';
import {Img, staticFile} from 'remotion';
import {useAnim, useJob} from '../ctx';
import {FPS} from '../time';
import {ThemeCtx} from '../studio/Blocks';
import {display} from '../studio/theme';
import {typedCount} from './typing';
import type {Block} from '../types';

// A quote card: the outlet on top (logo file, or its name set in serif), the quote
// typing in underneath. Goes in a section with full:true so it owns the canvas.
export const PullQuote = ({block}: {block: Extract<Block, {type: 'pullquote'}>}) => {
  const t = useContext(ThemeCtx);
  const {L} = useJob();
  const {frame, f, pop} = useAnim();
  const k = pop(block.at);
  const text = `“${block.text}”`;
  const count = typedCount(text.length, 5, (frame - f(block.at) - 8) / FPS);
  return (
    <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 60, opacity: k}}>
      {block.logo ? (
        <Img src={staticFile(block.logo)} style={{maxHeight: 150, maxWidth: '70%', objectFit: 'contain'}} />
      ) : (
        block.source && <div style={{fontFamily: 'Georgia, serif', fontWeight: 700, fontSize: L.portrait ? 72 : 96, color: t.ink, letterSpacing: -2}}>{block.source}</div>
      )}
      <div style={{position: 'relative', fontFamily: display, fontWeight: 600, fontSize: L.portrait ? 50 : 58, lineHeight: 1.28, textAlign: 'center', maxWidth: 1300}}>
        <span style={{visibility: 'hidden'}}>{text}</span>
        <span style={{position: 'absolute', inset: 0, color: t.ink}}>{text.slice(0, count)}</span>
      </div>
    </div>
  );
};
