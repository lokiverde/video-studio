import {Img, OffthreadVideo, Sequence, staticFile, interpolate} from 'remotion';
import {useAnim, useJob} from './ctx';
import {FPS} from './time';

const isVideo = (file: string) => /\.(mp4|mov|webm)$/i.test(file);
const fill = {position: 'absolute' as const, inset: 0, width: '100%', height: '100%', objectFit: 'cover' as const};

// One b-roll asset filling the frame from `from` to `to` (source seconds). Stills get a
// slow push. Clips play muted from their first frame, Tony's audio carries on underneath.
const Asset = ({file, from, to, fit = 'cover'}: {file: string; from: number; to: number; fit?: 'cover' | 'blur'}) => {
  const {frame, f} = useAnim();
  if (isVideo(file)) {
    return (
      <Sequence from={f(from)} durationInFrames={Math.max(1, f(to) - f(from))} layout="none">
        <OffthreadVideo src={staticFile(file)} muted style={fill} />
      </Sequence>
    );
  }
  const zoom = interpolate(frame, [f(from) - 10, f(from) + 170], [1.04, 1.16], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  if (fit === 'blur') {
    // the whole photo, framed, over a blurred copy of itself: nothing gets cropped off
    return (
      <>
        <Img src={staticFile(file)} style={{...fill, filter: 'blur(38px) brightness(.62)', transform: 'scale(1.25)'}} />
        <div style={{position: 'absolute', inset: '7%', display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${zoom - 0.06})`}}>
          <Img src={staticFile(file)} style={{maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: 14, boxShadow: '0 30px 80px rgba(0,0,0,.6)'}} />
        </div>
      </>
    );
  }
  return <Img src={staticFile(file)} style={{...fill, transform: `scale(${zoom})`}} />;
};

// Hook: assets split the window evenly, crossfade between them, fade out to Tony
export const BRoll = () => {
  const {job} = useJob();
  const {frame, f} = useAnim();
  const hook = job.hook;
  if (!hook || hook.broll.length === 0 || frame >= f(hook.to)) return null;
  const step = (hook.to - hook.from) / hook.broll.length;
  const out = interpolate(frame, [f(hook.to) - 10, f(hook.to)], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out, overflow: 'hidden', background: '#000'}}>
      {hook.broll.map((file, i) => {
        const start = hook.from + i * step;
        const op = i === 0 ? 1 : interpolate(frame, [f(start) - 8, f(start) + 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        return (
          <div key={file} style={{position: 'absolute', inset: 0, opacity: op}}>
            <Asset file={file} from={Math.max(hook.from, start - 0.3)} to={hook.to} />
          </div>
        );
      })}
    </div>
  );
};

// Mid-video cutaways: full screen for a few seconds, quick fade in and out
export const Cutaways = () => {
  const {job, L} = useJob();
  const {frame, f} = useAnim();
  // a news photo is landscape, so the 9:16 cut frames it instead of slicing it
  const fallback = job.style === 'news' && L.portrait ? 'blur' : 'cover';
  return (
    <>
      {(job.cutaways ?? []).map((c) => {
        if (frame < f(c.from) || frame >= f(c.to)) return null;
        const op = interpolate(frame, [f(c.from), f(c.from) + 6, f(c.to) - 6, f(c.to)], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        return (
          <div key={c.file + c.from} style={{position: 'absolute', inset: 0, opacity: op, overflow: 'hidden', background: '#000'}}>
            <Asset file={c.file} from={c.from} to={c.to} fit={c.fit ?? fallback} />
          </div>
        );
      })}
    </>
  );
};
