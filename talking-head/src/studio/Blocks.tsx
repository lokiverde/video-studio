import {createContext, useContext} from 'react';
import {Img, OffthreadVideo, Sequence, staticFile} from 'remotion';
import {useAnim} from '../ctx';
import type {Block} from '../types';
import {Icon} from './Icons';
import {THEMES, display, type Theme} from './theme';
import {PullQuote} from '../news/PullQuote';
import {Receipt} from './Receipt';

export const ThemeCtx = createContext<Theme>(THEMES.light);
const useTheme = () => useContext(ThemeCtx);

const Rise = ({at, children, y = 28}: {at: number; children: React.ReactNode; y?: number}) => {
  const k = useAnim().pop(at);
  return <div style={{opacity: k, transform: `translateY(${(1 - k) * y}px)`}}>{children}</div>;
};

const Source = ({text}: {text?: string}) => {
  const t = useTheme();
  if (!text) return null;
  return <div style={{fontFamily: display, fontSize: 30, color: t.mute, marginBottom: 8}}>{text}</div>;
};

const Headline = ({text, sub, at}: {text: string; sub?: string; at: number}) => {
  const t = useTheme();
  const k = useAnim().pop(at + 0.25, 200);
  return (
    <Rise at={at}>
      <div style={{fontFamily: display, fontWeight: 700, fontSize: 124, lineHeight: 1.0, letterSpacing: -4, color: t.ink, whiteSpace: 'pre-line'}}>{text}</div>
      <div style={{height: 3, width: `${k * 62}%`, background: t.ink, opacity: 0.8, marginTop: 18}} />
      {sub && <div style={{fontFamily: display, fontSize: 44, lineHeight: 1.25, color: t.mute, marginTop: 22}}>{sub}</div>}
    </Rise>
  );
};

const IconRow = ({kind, of, filled, at}: {kind: NonNullable<Extract<Block, {type: 'bigstat'}>['icons']>['kind']; of: number; filled: number; at: number}) => {
  const t = useTheme();
  const {pop} = useAnim();
  return (
    <div style={{display: 'flex', gap: 14, marginTop: 22}}>
      {Array.from({length: of}, (_, i) => {
        const k = pop(at + i * 0.08, 14);
        const on = i < filled;
        return (
          <div key={i} style={{transform: `scale(${k})`, opacity: on ? 1 : 0.55}}>
            <Icon name={kind} size={of > 6 ? 58 : 84} color={on ? t.accent : t.mute} filled={on && kind === 'person'} />
          </div>
        );
      })}
    </div>
  );
};

const BigStat = ({block}: {block: Extract<Block, {type: 'bigstat'}>}) => {
  const t = useTheme();
  return (
    <Rise at={block.at}>
      <Source text={block.source} />
      <div style={{fontFamily: display, fontWeight: 700, fontSize: 170, lineHeight: 0.95, letterSpacing: -6, color: t.ink}}>{block.value}</div>
      {block.label && <div style={{fontFamily: display, fontSize: 46, lineHeight: 1.25, color: t.mute, marginTop: 16, maxWidth: 860}}>{block.label}</div>}
      {block.icons && <IconRow {...block.icons} at={block.icons.at ?? block.at + 0.6} />}
    </Rise>
  );
};

const Steps = ({block}: {block: Extract<Block, {type: 'steps'}>}) => {
  const t = useTheme();
  const first = block.items[0]?.at ?? 0;
  return (
    <div>
      {block.title && (
        <Rise at={first - 0.4}>
          <div style={{fontFamily: display, fontWeight: 700, fontSize: 88, letterSpacing: -3, color: t.ink, marginBottom: 12}}>{block.title}</div>
          <div style={{height: 3, width: '70%', background: t.ink, opacity: 0.7, marginBottom: 30}} />
        </Rise>
      )}
      <div style={{display: 'flex', flexDirection: 'column', gap: 36}}>
        {block.items.map((it, i) => (
          <Rise key={it.text} at={it.at} y={20}>
            <div style={{display: 'flex', alignItems: 'center', gap: 22}}>
              <div style={{width: 76, height: 76, borderRadius: 38, border: `3px solid ${t.accent}`, color: t.ink, fontFamily: display, fontWeight: 600, fontSize: 38, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0}}>{i + 1}</div>
              {it.icon && <Icon name={it.icon} size={62} color={t.ink} />}
              <div>
                <div style={{fontFamily: display, fontWeight: 600, fontSize: 58, color: t.ink, letterSpacing: -0.5}}>{it.text}</div>
                {it.sub && <div style={{fontFamily: display, fontSize: 36, color: t.mute, marginTop: 4}}>{it.sub}</div>}
              </div>
            </div>
          </Rise>
        ))}
      </div>
    </div>
  );
};

const Bars = ({block}: {block: Extract<Block, {type: 'bars'}>}) => {
  const t = useTheme();
  const {pop} = useAnim();
  return (
    <div>
      <Source text={block.source} />
      <div style={{display: 'flex', flexDirection: 'column', gap: 22}}>
        {block.items.map((it, i) => {
          const k = pop(it.at, 200);
          return (
            <div key={it.label} style={{opacity: Math.min(1, k * 1.5)}}>
              <div style={{fontFamily: display, fontSize: 42, color: i === 0 ? t.ink : t.mute, marginBottom: 10}}>{it.label}</div>
              <div style={{height: 44, width: `${Math.max(4, it.value * 100 * k)}%`, borderRadius: 22, background: i === 0 ? t.accent : 'transparent', border: i === 0 ? 'none' : `3px solid ${t.mute}`, boxSizing: 'border-box'}} />
            </div>
          );
        })}
      </div>
    </div>
  );
};

// An example on screen: a screenshot or a clip in a rounded frame
const Screen = ({block}: {block: Extract<Block, {type: 'screen'}>}) => {
  const t = useTheme();
  const {f} = useAnim();
  const video = /\.(mp4|mov|webm)$/i.test(block.file);
  const media = {width: '100%', maxHeight: 740, objectFit: 'cover', objectPosition: 'top', display: 'block', borderRadius: 22} as const;
  return (
    <Rise at={block.at} y={50}>
      <div style={{background: '#fff', padding: 10, borderRadius: 30, boxShadow: '0 30px 80px rgba(0,0,0,.25)'}}>
        {video ? (
          <Sequence from={f(block.at)} layout="none">
            <OffthreadVideo src={staticFile(block.file)} muted style={media} />
          </Sequence>
        ) : (
          <Img src={staticFile(block.file)} style={media} />
        )}
      </div>
      {block.caption && <div style={{fontFamily: display, fontSize: 40, color: t.mute, marginTop: 20, textAlign: 'center'}}>{block.caption}</div>}
    </Rise>
  );
};

export const STUDIO_BLOCKS = new Set(['headline', 'bigstat', 'steps', 'bars', 'screen', 'pullquote', 'receipt']);

export const StudioBlockView = ({block}: {block: Block}) => {
  switch (block.type) {
    case 'headline':
      return <Headline {...block} />;
    case 'bigstat':
      return <BigStat block={block} />;
    case 'steps':
      return <Steps block={block} />;
    case 'bars':
      return <Bars block={block} />;
    case 'screen':
      return <Screen block={block} />;
    case 'pullquote':
      return <PullQuote block={block} />;
    case 'receipt':
      return <Receipt block={block} />;
    default:
      return null;
  }
};
