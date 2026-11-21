import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, spring} from 'remotion';
import {useJob} from './ctx';
import {FPS} from './time';
import {SPLIT_LIGHT, isSplit} from './split/geom';

// Soft landing: crossfades in over the last beat of footage, holds, then fades to black
export const EndCard = () => {
  const frame = useCurrentFrame();
  const {job, time, brand, L} = useJob();
  const end = job.endCard;
  if (!end) return null;
  const start = time.bodyFrames - 12;
  if (frame < start) return null;
  const inK = interpolate(frame, [start, time.bodyFrames + 6], [0, 1], {extrapolateRight: 'clamp'});
  const outK = interpolate(frame, [time.totalFrames - 14, time.totalFrames - 1], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const rise = spring({frame: frame - start - 6, fps: FPS, config: {damping: 18}});
  const big = L.portrait ? 92 : 120;
  // army: the headline drawn by army.py as a words graphic, same type as the rest of the video
  if (job.army?.end) {
    return (
      <AbsoluteFill style={{background: '#000', opacity: inK}}>
        <Img src={staticFile(job.army.end)} style={{width: '100%', height: '100%', opacity: outK, transform: `scale(${1.04 - 0.04 * rise})`}} />
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{background: '#000', opacity: inK}}>
      <AbsoluteFill style={{background: brand.navy, opacity: outK, alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: 80}}>
        {end.kicker && <div style={{fontFamily: 'Helvetica Neue, Arial', fontWeight: 700, fontSize: L.portrait ? 30 : 32, letterSpacing: 5, color: isSplit(job) ? SPLIT_LIGHT : brand.amber, textTransform: 'uppercase'}}>{end.kicker}</div>}
        <div style={{fontFamily: 'Georgia, serif', fontWeight: 700, fontSize: big, color: '#fff', margin: '18px 0', transform: `translateY(${(1 - rise) * 30}px)`}}>{end.headline}</div>
        {end.sub && <div style={{fontFamily: 'Helvetica Neue, Arial', fontSize: L.portrait ? 34 : 36, color: 'rgba(255,255,255,.8)', maxWidth: 1100}}>{end.sub}</div>}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
