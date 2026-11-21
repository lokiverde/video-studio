import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {alpha, useAnton} from './anim';
import {Compare} from './Compare';
import {List} from './List';
import {Punch} from './Punch';
import type {MographProps, Palette} from './types';

// A motion graphic scene of a faceless video (docs/mograph.md). Props come from
// scripts/mograph.py; this draws the canvas and hands the scene to its kind.

const Canvas = ({palette, frames}: {palette: Palette; frames: number}) => {
  const frame = useCurrentFrame();
  // The glow drifts and the grid slides a little, so a held frame never reads as frozen.
  const drift = interpolate(frame, [0, Math.max(1, frames)], [0, 1]);
  const glowX = 14 + drift * 8;
  const background = [
    `radial-gradient(ellipse 70% 60% at ${glowX}% 8%, ${alpha(palette.accent, 0.2)} 0%, ${alpha(palette.accent, 0)} 70%)`,
    `radial-gradient(ellipse 80% 70% at 92% 105%, ${palette.bg_deep} 0%, ${alpha(palette.bg_deep, 0)} 70%)`,
    palette.bg,
  ].join(', ');
  const grid = alpha(palette.text, 0.035);
  return (
    <AbsoluteFill style={{background}}>
      <AbsoluteFill
        style={{
          backgroundImage: `repeating-linear-gradient(0deg, ${grid} 0 1px, transparent 1px 64px), repeating-linear-gradient(90deg, ${grid} 0 1px, transparent 1px 64px)`,
          backgroundPosition: `${-drift * 32}px ${-drift * 16}px`,
        }}
      />
      <AbsoluteFill style={{boxShadow: `inset 0 0 260px ${alpha(palette.bg_deep, 0.85)}`}} />
    </AbsoluteFill>
  );
};

export const Mograph = (props: MographProps) => {
  const frame = useCurrentFrame();
  const ready = useAnton();
  // A slow push in over the whole scene keeps the camera alive after everything lands.
  const push = interpolate(frame, [0, Math.max(1, props.frames)], [1, 1.035]);
  return (
    <AbsoluteFill>
      <Canvas palette={props.palette} frames={props.frames} />
      {ready && (
        <AbsoluteFill style={{transform: `scale(${push})`}}>
          {props.kind === 'compare' && <Compare {...props} />}
          {props.kind === 'punch' && <Punch {...props} />}
          {props.kind === 'list' && <List {...props} />}
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
