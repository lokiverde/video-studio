import {useContext} from 'react';
import {Img, interpolate, staticFile, Easing} from 'remotion';
import {useAnim, useJob} from '../ctx';
import type {Block} from '../types';
import {display} from './theme';
import {SplitCtx} from '../split/geom';

const PUSH_S = 5;
// [start, end] zoom toward the quote. 9:16 starts already zoomed in: a phone shows the
// whole comment too small to read, the quoted lines are what matter there. The 16:9 split
// card barely pushes: the quote lifting off the page is the move there. The 9:16 split card
// is shorter than the screen, so it starts zoomed in like full 9:16, edge to edge.
const PUSH = {landscape: [1, 1.14], portrait: [1.12, 1.35], split: [1, 1.05], splitPortrait: [1.2, 1.32]} as const;
// 9:16 keeps receipts above the key-word captions
const PORTRAIT_MAX_H = 860;
const LINE_STAGGER_S = 0.22;
const LIFT_AFTER_S = 0.35;
// split: Brokerage light blue highlighter and ring (#29a8d6)
const MARK = {board: 'rgba(255, 213, 0, .45)', split: 'rgba(41, 168, 214, .30)'};
const LIFT_RING = 'rgba(204, 238, 252, 1)';

type Box = [number, number, number, number];
type ReceiptBlock = Extract<Block, {type: 'receipt'}>;

// The highlighter boxes, swept left to right one line after another. `within` maps them
// into a cropped copy of the image (the lifted quote).
const Marks = ({block, color, within}: {block: ReceiptBlock; color: string; within?: Box}) => {
  const {pop} = useAnim();
  const [ox, oy, ow, oh] = within ?? [0, 0, 1, 1];
  return (
    <>
      {(block.lines ?? (block.highlight ? [block.highlight] : [])).map(([x, y, w, h], i) => {
        const sweep = pop(block.at + 0.5 + i * LINE_STAGGER_S, 200);
        return (
          <div
            key={i}
            style={{position: 'absolute', left: `${((x - ox) / ow) * 100}%`, top: `${((y - oy) / oh) * 100}%`, width: `${(w / ow) * 100 * sweep}%`, height: `${(h / oh) * 100}%`, background: color, mixBlendMode: 'multiply', borderRadius: 6}}
          />
        );
      })}
    </>
  );
};

// Split layout: once the sweep is done the quote rises off the screenshot, a little bigger,
// on a soft ring and shadow, like the pulled-out line in the reference
const Lift = ({block, box}: {block: ReceiptBlock; box: Box}) => {
  const {pop} = useAnim();
  const [hx, hy, hw, hh] = box;
  const lines = block.lines?.length ?? 1;
  const k = pop(block.at + 0.5 + lines * LINE_STAGGER_S + LIFT_AFTER_S, 14);
  if (k <= 0.01) return null;
  return (
    <div
      style={{
        position: 'absolute',
        left: `${hx * 100}%`,
        top: `${hy * 100}%`,
        width: `${hw * 100}%`,
        height: `${hh * 100}%`,
        overflow: 'hidden',
        borderRadius: 8,
        background: '#fff',
        transform: `translateY(${-8 * k}px) scale(${1 + 0.06 * k})`,
        boxShadow: `0 0 0 ${6 * k}px ${LIFT_RING}, 0 ${16 * k}px ${40 * k}px rgba(20,20,30,${0.26 * k})`,
      }}
    >
      <Img src={staticFile(block.file)} style={{position: 'absolute', left: `${(-hx / hw) * 100}%`, top: `${(-hy / hh) * 100}%`, width: `${100 / hw}%`, maxWidth: 'none'}} />
      <Marks block={block} color={MARK.split} within={box} />
    </div>
  );
};

// Board style receipt: a real screenshot. The quoted line gets a highlighter sweep, then the
// frame pushes slowly toward it (full screen) or the quote lifts off the page (split card).
// Handles are blurred in the PNG itself.
export const Receipt = ({block}: {block: ReceiptBlock}) => {
  const {L} = useJob();
  const split = useContext(SplitCtx);
  const {frame, f, pop} = useAnim();
  const k = pop(block.at, 16);
  const [hx, hy, hw, hh] = block.highlight ?? [0, 0, 0, 0];
  const mode = split ? (L.portrait ? 'splitPortrait' : 'split') : L.portrait ? 'portrait' : 'landscape';
  const [z0, z1] = PUSH[mode];
  // 16:9 split lets the lifted quote rise past the screenshot's edge; every other mode
  // zooms inside the screenshot's own frame
  const clip = mode !== 'split';
  const push = interpolate(frame, [f(block.at + 0.6), f(block.at + 0.6 + PUSH_S)], block.highlight ? [z0, z1] : [1, 1.04], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.quad),
  });
  // 9:16 zooms from the quote's left edge, so its lines start clean and only the right crops
  const originX = L.portrait ? hx : hx + hw / 2;
  const origin = block.highlight ? `${originX * 100}% ${(hy + hh / 2) * 100}%` : '50% 30%';
  // split: fill the card's canvas, measured in the block column's own (scaled) units
  const maxW = split ? (split.w - (L.portrait ? 24 : 80)) / split.scale : L.portrait ? L.W - 40 : L.fullPanel.w - 40;
  const maxH = split ? (split.h - (block.source ? 150 : 90)) / split.scale : L.portrait ? PORTRAIT_MAX_H : L.fullPanel.h - (block.source ? 110 : 40);
  const shadow = split ? '0 18px 50px rgba(20,20,30,.16), 0 0 0 1px rgba(0,0,0,.06)' : '0 40px 100px rgba(0,0,0,.55), 0 0 0 1px rgba(255,255,255,.08)';
  return (
    <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: k, transform: `translateY(${(1 - k) * 50}px) scale(${0.96 + 0.04 * k})`}}>
      {/* unclipped: the shadow rides the push and the lifted quote may rise past the edge */}
      <div style={{position: 'relative', display: 'inline-block', overflow: clip ? 'hidden' : 'visible', borderRadius: 20, boxShadow: clip ? shadow : 'none'}}>
        <div style={{position: 'relative', transform: `scale(${push})`, transformOrigin: origin, ...(clip ? {} : {borderRadius: 20, overflow: 'hidden', boxShadow: shadow})}}>
          <Img src={staticFile(block.file)} style={{display: 'block', maxWidth: maxW, maxHeight: maxH}} />
          <Marks block={block} color={split ? MARK.split : MARK.board} />
        </div>
        {split && block.highlight && (
          <div style={{position: 'absolute', inset: 0, transform: `scale(${push})`, transformOrigin: origin}}>
            <Lift block={block} box={block.highlight} />
          </div>
        )}
      </div>
      {block.source && <div style={{fontFamily: display, fontSize: L.portrait && !split ? 34 : 30, color: split ? '#6a6f77' : '#93a1b5', marginTop: 26, letterSpacing: 1}}>{block.source}</div>}
    </div>
  );
};
