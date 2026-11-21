import {interpolate} from 'remotion';
import {useAnim, useJob} from '../ctx';
import type {Block, Part} from '../types';
import {STUDIO_BLOCKS, StudioBlockView} from '../studio/Blocks';

const sans = 'Helvetica Neue, Arial, sans-serif';
const serif = 'Georgia, serif';
const cardShadow = '0 18px 50px rgba(15,42,67,.14)';

const Rise = ({at, children, y = 40}: {at: number; children: React.ReactNode; y?: number}) => {
  const k = useAnim().pop(at);
  return <div style={{opacity: k, transform: `translateY(${(1 - k) * y}px)`}}>{children}</div>;
};

// Source-document card: real text, highlights sweep in on cue
const Statute = ({cite, heading, source, parts}: {cite: string; heading?: string; source?: string; parts: Part[]}) => {
  const {brand} = useJob();
  const {pop} = useAnim();
  return (
    <div style={{background: '#fff', borderRadius: 20, padding: '44px 52px', boxShadow: cardShadow, border: '1px solid #e6e2d8'}}>
      <div style={{fontFamily: sans, fontSize: 22, letterSpacing: 2, color: brand.mute, textTransform: 'uppercase'}}>{source ?? 'California Civil Code · leginfo.legislature.ca.gov'}</div>
      <div style={{fontFamily: serif, fontSize: 46, fontWeight: 700, color: brand.navy, margin: '10px 0 6px'}}>{cite}</div>
      {heading && <div style={{fontFamily: sans, fontSize: 24, color: brand.mute, marginBottom: 22}}>{heading}</div>}
      <div style={{fontFamily: serif, fontSize: 33, lineHeight: 1.5, color: brand.ink}}>
        {parts.map((p, i) => {
          if (typeof p === 'string') return <span key={i}>{p}</span>;
          const k = pop(p.at, 200);
          return (
            <span key={i} style={{backgroundImage: 'linear-gradient(#ffe45c,#ffe45c)', backgroundRepeat: 'no-repeat', backgroundSize: `${k * 100}% 100%`, borderRadius: 4, fontWeight: k > 0.5 ? 700 : 400}}>
              {p.hl}
            </span>
          );
        })}
      </div>
    </div>
  );
};

const Quote = ({text, at, xAt}: {text: string; at: number; xAt?: number}) => {
  const {brand} = useJob();
  const {pop} = useAnim();
  const x = xAt === undefined ? 0 : pop(xAt, 12);
  return (
    <Rise at={at}>
      <div style={{position: 'relative', background: '#fff', borderLeft: `12px solid ${brand.amber}`, borderRadius: 16, padding: xAt === undefined ? '40px 48px' : '40px 230px 40px 48px', boxShadow: cardShadow}}>
        <div style={{fontFamily: serif, fontStyle: 'italic', fontSize: 58, lineHeight: 1.25, color: brand.ink, opacity: 1 - x * 0.45}}>{text}</div>
        {xAt !== undefined && (
          <div style={{position: 'absolute', right: 40, top: '50%', marginTop: -115, lineHeight: '230px', fontFamily: sans, fontSize: 190, fontWeight: 900, color: brand.red, opacity: x, transform: `scale(${interpolate(x, [0, 1], [2.2, 1])}) rotate(-8deg)`}}>✕</div>
        )}
      </div>
    </Rise>
  );
};

const Strike = ({value, note, at, noteAt}: {value: string; note: string; at: number; noteAt: number}) => {
  const {brand} = useJob();
  const {pop} = useAnim();
  return (
    <Rise at={at}>
      <div style={{display: 'flex', alignItems: 'center', gap: 36}}>
        <div style={{position: 'relative', fontFamily: serif, fontSize: 96, fontWeight: 700, color: brand.mute}}>
          {value}
          <div style={{position: 'absolute', left: -8, top: '52%', height: 9, width: `${pop(at + 0.5, 200) * 108}%`, background: brand.red, borderRadius: 5}} />
        </div>
        <div style={{opacity: pop(noteAt), fontFamily: sans, fontSize: 40, fontWeight: 700, color: '#fff', background: brand.red, padding: '12px 26px', borderRadius: 12}}>{note}</div>
      </div>
    </Rise>
  );
};

const Bar = ({label, at, dangerAt, noteAt, note}: {label?: string; at: number; dangerAt?: number; noteAt?: number; note?: string}) => {
  const {brand} = useJob();
  const {pop} = useAnim();
  const grow = pop(at, 200);
  const danger = dangerAt === undefined ? 0 : pop(dangerAt);
  const zones = [
    {w: 30, c: brand.red, l: 'Under 30%', s: 'Special assessment risk'},
    {w: 40, c: brand.yellow, l: '30 to 70%', s: 'Watch zone'},
    {w: 30, c: brand.green, l: 'Over 70%', s: 'Strong'},
  ];
  return (
    <Rise at={at}>
      <div style={{fontFamily: sans, fontSize: 26, letterSpacing: 3, color: brand.mute, textTransform: 'uppercase', fontWeight: 700, margin: '8px 0 14px'}}>{label ?? 'Percent funded'}</div>
      <div style={{display: 'flex', width: `${grow * 100}%`, height: 64, borderRadius: 14, overflow: 'hidden'}}>
        {zones.map((z, i) => (
          <div key={z.l} style={{width: `${z.w}%`, background: z.c, filter: i === 0 ? `brightness(${1 + danger * 0.18})` : `saturate(${1 - danger * 0.5})`}} />
        ))}
      </div>
      <div style={{display: 'flex', marginTop: 12, opacity: grow}}>
        {zones.map((z) => (
          <div key={z.l} style={{width: `${z.w}%`, fontFamily: sans}}>
            <div style={{fontSize: 30, fontWeight: 700, color: brand.ink}}>{z.l}</div>
            <div style={{fontSize: 22, color: brand.mute}}>{z.s}</div>
          </div>
        ))}
      </div>
      {note && noteAt !== undefined && <div style={{opacity: pop(noteAt), marginTop: 22, fontFamily: sans, fontSize: 34, fontWeight: 700, color: brand.red}}>{note}</div>}
    </Rise>
  );
};

export const BlockView = ({block}: {block: Block}) => {
  const {brand} = useJob();
  const {pop} = useAnim();
  if (STUDIO_BLOCKS.has(block.type)) return <StudioBlockView block={block} />;
  switch (block.type) {
    case 'statute':
      return <Statute {...block} />;
    case 'quote':
      return <Quote {...block} />;
    case 'strike':
      return <Strike {...block} />;
    case 'bar':
      return <Bar {...block} />;
    case 'note':
      return (
        <Rise at={block.at}>
          <div style={{fontFamily: sans, fontSize: 35, fontWeight: 700, color: block.color === 'red' ? brand.red : brand.navy}}>{block.text}</div>
        </Rise>
      );
    case 'stat':
      return (
        <Rise at={block.at}>
          <div style={{fontFamily: sans, fontSize: 26, letterSpacing: 3, color: brand.red, textTransform: 'uppercase', fontWeight: 700}}>{block.label}</div>
          <div style={{fontFamily: serif, fontSize: 120, fontWeight: 700, color: brand.navy, lineHeight: 1.05}}>{block.value}</div>
        </Rise>
      );
    case 'list':
      return (
        <div style={{display: 'flex', flexDirection: 'column', gap: 18}}>
          {block.items.map((it) => (
            <Rise key={it.name} at={it.at} y={24}>
              <div style={{display: 'flex', alignItems: 'baseline', gap: 24, background: '#fff', borderRadius: 14, padding: '20px 30px', border: '1px solid #e6e2d8'}}>
                <div style={{fontFamily: serif, fontSize: 46, fontWeight: 700, color: brand.navy, minWidth: 330}}>{it.name}</div>
                {it.who && <div style={{fontFamily: sans, fontSize: 28, color: brand.mute}}>{it.who}</div>}
              </div>
            </Rise>
          ))}
        </div>
      );
    case 'formula':
      return (
        <Rise at={block.at}>
          <div style={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 22, fontFamily: serif, fontWeight: 700, color: brand.navy}}>
            {block.terms.map((term, i) => (
              <div key={term} style={{display: 'flex', alignItems: 'center', gap: 22}}>
                {i > 0 && <div style={{fontSize: 64, color: brand.amber}}>+</div>}
                <div style={{background: '#fff', border: `3px solid ${brand.navy}`, borderRadius: 16, padding: '18px 28px', fontSize: 48}}>{term}</div>
              </div>
            ))}
          </div>
          {block.caption && <div style={{fontFamily: sans, fontSize: 26, color: brand.mute, marginTop: 12}}>{block.caption}</div>}
        </Rise>
      );
    case 'traffic':
      return (
        <div style={{display: 'flex', flexDirection: 'column', gap: 22}}>
          {block.items.map((it) => {
            const k = pop(it.at);
            return (
              <div key={it.title} style={{display: 'flex', gap: 26, alignItems: 'center', background: '#fff', borderRadius: 18, padding: '26px 32px', border: '1px solid #e6e2d8', opacity: 0.25 + k * 0.75, transform: `scale(${0.97 + k * 0.03})`, boxShadow: k > 0.5 ? cardShadow : 'none'}}>
                <div style={{width: 64, height: 64, borderRadius: 32, background: brand[it.color], flexShrink: 0}} />
                <div>
                  <div style={{fontFamily: serif, fontSize: 44, fontWeight: 700, color: brand.navy}}>{it.title}</div>
                  {it.body && <div style={{fontFamily: sans, fontSize: 28, color: brand.mute}}>{it.body}</div>}
                </div>
              </div>
            );
          })}
        </div>
      );
    case 'cta':
      return (
        <Rise at={block.at}>
          <div style={{background: brand.navy, borderRadius: 18, padding: '26px 34px'}}>
            {block.kicker && <div style={{fontFamily: sans, fontSize: 26, letterSpacing: 3, color: brand.amber, fontWeight: 700, textTransform: 'uppercase'}}>{block.kicker}</div>}
            <div style={{fontFamily: serif, fontSize: 64, fontWeight: 700, color: '#fff'}}>{block.headline}</div>
          </div>
        </Rise>
      );
  }
};
