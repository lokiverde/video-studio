import {AbsoluteFill} from 'remotion';
import {JobCtx, useAnim, useJob} from './ctx';
import {FPS, makeTime} from './time';
import {DEFAULT_BRAND, isStudio, type Job, type Section} from './types';
import {LANDSCAPE, PORTRAIT, PANEL_W, STUDIO_LANDSCAPE, STUDIO_PORTRAIT, mirrorX} from './layout';
import {TonyLayer} from './TonyLayer';
import {BRoll, Cutaways} from './BRoll';
import {EndCard} from './EndCard';
import {BlockView} from './panels/Blocks';
import {ThemeCtx} from './studio/Blocks';
import {THEMES, canvasCss, themeOf} from './studio/theme';
import {Stickers, Typed} from './news/Overlays';
import {Captions, Counter, Disclaimer, LowerThird, Phrases, QuestionTags, Title} from './Overlays';
import {Board} from './Board';
import {nextGraphicStart} from './boardSpans';
import {KeyCaptions} from './KeyCaptions';
import {SPLIT_BACKDROP, isSplit} from './split/geom';
import {SplitStage} from './split/SplitStage';
import {NumberWipe} from './split/NumberWipe';
import {ARMY_NAVY, isArmy} from './army/geom';
import {ArmyCanvas, ArmyGraphics, ArmyLines} from './army/ArmyStage';
import {ArmySplitStage, ArmyWipe} from './army/ArmySplitStage';

// board style: full-screen blocks sit in a centered column instead of hugging the left edge
const BOARD_COL_W = 1240;
const FADE_F = 8;

// One evidence panel, visible only inside its section window
const Panel = ({section}: {section: Section}) => {
  const {job, L} = useJob();
  const {windowFade} = useAnim();
  const board = job.style === 'board';
  // board: hold until the next graphic starts and crossfade into it (no empty canvas between)
  const next = board ? nextGraphicStart(job, section.evidence[1]) : null;
  const start = board ? section.evidence[0] : section.evidence[0] + 0.15;
  const end = next !== null ? next + FADE_F / FPS : section.evidence[1];
  const k = windowFade(start, end, FADE_F);
  if (k <= 0) return null;
  const studio = isStudio(job);
  // board style: every section is a full-screen graphic on the glow theme
  const full = studio && (section.full || board);
  const sided = studio && !L.portrait && section.side === 'left' ? mirrorX(L.panel, L.W) : L.panel;
  const rect = full ? {...L.fullPanel, scale: 1} : sided;
  const width = full ? (board ? Math.min(L.fullPanel.w, BOARD_COL_W) : L.fullPanel.w) : PANEL_W;
  const theme = themeOf(section.theme ?? (board ? 'glow' : undefined));
  return (
    <ThemeCtx.Provider value={theme}>
      {studio && <div style={{position: 'absolute', inset: 0, background: canvasCss(theme), opacity: k}} />}
      <div style={{position: 'absolute', left: rect.x, top: rect.y, width: rect.w, height: rect.h, opacity: k, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: board ? 'center' : undefined}}>
        <div style={{width, transform: `scale(${rect.scale})`, transformOrigin: 'left center', display: 'flex', flexDirection: 'column', gap: studio ? 44 : 24}}>
          {section.blocks.map((b, i) => (
            <BlockView key={i} block={b} />
          ))}
        </div>
      </div>
    </ThemeCtx.Provider>
  );
};

export const Main = ({job, portrait}: {job: Job; portrait: boolean}) => {
  const army = isArmy(job);
  // army: Brokerage navy for the name bar and the end card
  const brand = {...DEFAULT_BRAND, ...(army ? {navy: ARMY_NAVY} : {}), ...job.brand};
  const studio = isStudio(job);
  const L = studio ? (portrait ? STUDIO_PORTRAIT : STUDIO_LANDSCAPE) : portrait ? PORTRAIT : LANDSCAPE;
  const ctx = {job, time: makeTime(job), brand, L};
  const split = isSplit(job);
  // board sits on the dark glow canvas, so a gap between graphics never flashes paper;
  // split shows its pale backdrop wherever Tony and the card are not
  const root = army ? ARMY_NAVY : split ? SPLIT_BACKDROP : job.style === 'board' ? canvasCss(THEMES.glow) : `radial-gradient(circle at 20% 10%, #ffffff 0%, ${brand.paper} 55%, #efece4 100%)`;
  return (
    <JobCtx.Provider value={ctx}>
      <AbsoluteFill style={{background: root}}>
        {!split &&
          job.sections.map((s, i) => (
            <Panel key={i} section={s} />
          ))}
        {army && <ArmyCanvas />}
        <TonyLayer />
        {army && <ArmyLines />}
        {army && <ArmySplitStage />}
        {split && <SplitStage />}
        <Stickers />
        <BRoll />
        <Cutaways />
        {army && <ArmyGraphics />}
        <Board />
        <Typed />
        <Title />
        <LowerThird />
        <Counter />
        <QuestionTags />
        <Disclaimer />
        <Captions />
        <KeyCaptions />
        <Phrases />
        <NumberWipe />
        {army && <ArmyWipe />}
        <EndCard />
      </AbsoluteFill>
    </JobCtx.Provider>
  );
};
