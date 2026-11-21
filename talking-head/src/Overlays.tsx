import {interpolate} from 'remotion';
import {useAnim, useJob} from './ctx';
import {FPS} from './time';
import {isStudio} from './types';
import {KEY_FONT, keyCaptionBox, keyColor, keyFontSize} from './KeyCaptions';
import {SPLIT_ACCENT, SPLIT_LIGHT, isSplit} from './split/geom';
import {ARMY_CAPTION_BG, armyCaptionBox, splitAmount as armySplitAmount} from './army/geom';

const sans = 'Helvetica Neue, Arial, sans-serif';
const serif = 'Georgia, serif';

// Running captions. Studio and news styles leave them off in 16:9 (phrases and typed
// lines carry the emphasis)
// and keeps them in 9:16, where most people watch muted.
const captionsOn = (mode: string, studio: boolean, portrait: boolean) => {
  if (mode === 'off' || mode === 'phrases') return false;
  if (mode === 'full') return true;
  return !studio || portrait;
};

export const Captions = () => {
  const {job, time, L} = useJob();
  const {frame, f} = useAnim();
  // board style draws its own key-word captions (KeyCaptions)
  if (job.style === 'board') return null;
  // army: captions on in both cuts, in the band under the graphics and the punch line
  const army = job.style === 'army';
  if (!captionsOn(job.captionMode ?? (army ? 'full' : 'auto'), isStudio(job), L.portrait)) return null;
  if (frame >= time.bodyFrames - 6) return null;
  const t = frame / FPS;
  const cap = (job.captions ?? []).find((c) => t >= c.s && t < c.e);
  if (!cap) return null;
  // a kinetic phrase owns the screen while it is up, captions step aside
  if ((job.phrases ?? []).some((p) => frame >= f(p.from) && frame < f(p.to))) return null;
  const covered = (job.cutaways ?? []).some((c) => frame >= f(c.from) && frame < f(c.to));
  const inCard = !covered && job.sections.some((s) => frame >= f(s.evidence[0]) + 6 && frame < f(s.evidence[1]));
  // army split: captions sit in the graphics card's bottom band, which army.py leaves free.
  // A full-screen graphic inside a split run hides the card, so its caption drops to the frame band
  const fullGraphic = army && (job.army?.beats ?? []).some((b) => b.layout === 'graphic' && frame >= f(b.from) && frame < f(b.to));
  const band = army && job.army && !fullGraphic && armySplitAmount(job, time, frame) > 0.5 ? job.army.split.caption : null;
  const pos = band ? {left: band.x, width: band.w, top: band.y} : army ? armyCaptionBox(L.portrait) : inCard ? L.caption.card : L.caption.full;
  const bg = army ? ARMY_CAPTION_BG : 'rgba(15,32,50,.82)';
  return (
    <div style={{position: 'absolute', display: 'flex', justifyContent: 'center', ...pos}}>
      <div style={{fontFamily: sans, fontWeight: 700, fontSize: inCard ? L.caption.cardFont : L.caption.fullFont, color: '#fff', background: bg, padding: '10px 22px', borderRadius: 12, textAlign: 'center', maxWidth: inCard ? L.caption.cardMax : L.caption.fullMax}}>{cap.t}</div>
    </div>
  );
};

export const Title = () => {
  const {job, L} = useJob();
  const {pop, windowFade} = useAnim();
  const hook = job.hook;
  if (!hook) return null;
  const k = pop(hook.from + 0.4) * windowFade(hook.from, hook.to);
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', paddingLeft: L.title.pad, paddingRight: L.title.pad, opacity: k, background: L.title.gradient}}>
      {hook.kicker && <div style={{fontFamily: sans, fontWeight: 700, fontSize: 30, letterSpacing: 5, color: '#f2a93b', textTransform: 'uppercase'}}>{hook.kicker}</div>}
      <div style={{fontFamily: serif, fontWeight: 700, fontSize: L.title.font, lineHeight: 1.05, color: '#fff', maxWidth: L.title.maxW, whiteSpace: 'pre-line', transform: `translateY(${(1 - k) * 30}px)`}}>{hook.title}</div>
    </div>
  );
};

export const LowerThird = () => {
  const {job, brand, L} = useJob();
  const {pop, windowFade} = useAnim();
  const items = !job.lowerThird ? [] : Array.isArray(job.lowerThird) ? job.lowerThird : [job.lowerThird];
  // split layout: Brokerage light blue strip under the navy bar instead of amber
  const strip = isSplit(job) || job.style === 'army' ? {background: SPLIT_LIGHT, color: SPLIT_ACCENT} : {background: brand.amber, color: brand.ink};
  return (
    <>
      {items.map((lt) => {
        const k = pop(lt.from) * windowFade(lt.from, lt.to);
        return (
          <div key={lt.from} style={{position: 'absolute', ...L.lowerThird, opacity: k, transform: `translateX(${(1 - k) * -60}px)`}}>
            <div style={{background: brand.navy, color: '#fff', fontFamily: serif, fontWeight: 700, fontSize: 52, padding: '14px 30px', borderRadius: '14px 14px 14px 0', display: 'inline-block'}}>{lt.name}</div>
            <div />
            <div style={{...strip, fontFamily: sans, fontWeight: 700, fontSize: L.portrait ? 24 : 28, padding: '8px 30px', borderRadius: '0 0 14px 14px', display: 'inline-block'}}>{lt.line}</div>
          </div>
        );
      })}
    </>
  );
};

export const QuestionTags = () => {
  const {job, brand, L} = useJob();
  const {pop, windowFade} = useAnim();
  return (
    <>
      {job.sections.map((s) => {
        if (!s.tag) return null;
        const k = pop(s.tag.from, 14) * windowFade(s.tag.from, s.tag.to, 6);
        return (
          <div key={s.tag.n} style={{position: 'absolute', ...L.tag.style, display: 'flex', alignItems: 'center', gap: 24, opacity: k, transform: `scale(${interpolate(k, [0, 1], [0.8, 1])})`, transformOrigin: 'left top'}}>
            <div style={{width: L.tag.dot, height: L.tag.dot, borderRadius: L.tag.dot / 2, background: brand.amber, color: brand.ink, fontFamily: serif, fontWeight: 700, fontSize: L.tag.dot * 0.68, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0}}>{s.tag.n}</div>
            <div style={{fontFamily: sans, fontWeight: 800, fontSize: L.tag.font, color: '#fff', textShadow: '0 4px 24px rgba(0,0,0,.7)'}}>{s.tag.topic}</div>
          </div>
        );
      })}
    </>
  );
};

export const Counter = () => {
  const {job, brand, L} = useJob();
  const {pop, windowFade} = useAnim();
  const c = job.counter;
  if (!c) return null;
  const fade = windowFade(c.from, c.to, 6);
  return (
    <div style={{position: 'absolute', ...L.counter, display: 'flex', flexDirection: 'column', gap: 14, opacity: fade}}>
      {Array.from({length: c.count}, (_, i) => (
        <div key={i} style={{width: 84, height: 84, borderRadius: 42, background: brand.amber, color: brand.ink, fontFamily: serif, fontWeight: 700, fontSize: 52, display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${pop(c.from + i * 0.16, 12)})`}}>{i + 1}</div>
      ))}
    </div>
  );
};

export const Disclaimer = () => {
  const {job, L} = useJob();
  const {pop} = useAnim();
  if (!job.disclaimer) return null;
  return (
    <div style={{position: 'absolute', left: 40, right: 40, top: L.disclaimerTop, textAlign: 'center', opacity: pop(job.disclaimer.from), fontFamily: sans, fontSize: 28, color: '#fff', textShadow: '0 2px 14px rgba(0,0,0,.8)'}}>{job.disclaimer.text}</div>
  );
};

// Kinetic phrases: one line over Tony, the `em` word gets an underline that sweeps in.
// Board style colors the `em` word gold instead.
export const Phrases = () => {
  const {job, L} = useJob();
  const {pop, windowFade} = useAnim();
  const board = job.style === 'board';
  return (
    <>
      {(job.phrases ?? []).map((p) => {
        const k = pop(p.from, 16) * windowFade(p.from, p.to, 6);
        if (k <= 0.001) return null;
        const line = pop(p.from + 0.35, 200);
        const side = p.pos === 'side' && !L.portrait;
        const box: React.CSSProperties = board
          ? keyCaptionBox(L.portrait)
          : side
            ? {left: 110, top: 300, width: 620, textAlign: 'left'}
            : {left: 0, right: 0, bottom: L.portrait ? 470 : 120, textAlign: 'center'};
        // board phrases read as the key-word captions they replace, same place and type
        const type: React.CSSProperties = board
          ? {...KEY_FONT, fontSize: keyFontSize(L.portrait)}
          : {fontFamily: sans, fontWeight: 700, fontSize: L.portrait ? 60 : 58, lineHeight: 1.15, letterSpacing: -1, color: '#fff', textShadow: '0 4px 30px rgba(0,0,0,.75)'};
        const parts = p.em && p.text.includes(p.em) ? p.text.split(p.em) : [p.text];
        return (
          <div key={p.from} style={{position: 'absolute', ...box, padding: board ? 0 : '0 60px', opacity: k, transform: `translateY(${(1 - k) * 18}px)`}}>
            <span style={type}>
              {parts[0]}
              {parts.length > 1 && (
                <span style={{position: 'relative', display: 'inline-block', color: board ? keyColor(isSplit(job)) : undefined}}>
                  {p.em}
                  {!board && <span style={{position: 'absolute', left: 0, bottom: -6, height: 6, width: `${line * 100}%`, background: '#f2a93b', borderRadius: 3}} />}
                </span>
              )}
              {parts.slice(1).join(p.em)}
            </span>
          </div>
        );
      })}
    </>
  );
};
