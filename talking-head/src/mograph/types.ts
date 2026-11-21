// Props for the Mograph composition, written by scripts/mograph.py (props()).
// Times (`at`) are seconds from the start of the scene.

export type Palette = {bg: string; bg_deep: string; text: string; accent: string; accent_hi: string; dim: string};

type Base = {portrait: boolean; fps: number; frames: number; palette: Palette};

export type CompareProps = Base & {
  kind: 'compare';
  title: string;
  source: string;
  prefix: string;
  suffix: string;
  decimals: number;
  highlight: number;
  items: Array<{label: string; value: number; text: string; at: number}>;
};

export type PunchProps = Base & {kind: 'punch'; text: string; em: string[]; kicker: string; sub: string};

export type ListProps = Base & {
  kind: 'list';
  title: string;
  numbered: boolean;
  items: Array<{text: string; sub: string; at: number}>;
};

export type MographProps = CompareProps | PunchProps | ListProps;

// The safe box every layout stays inside: clear of the burned-in caption band at the
// bottom (assemble.py: 90px margin in 16:9, 330px in 9:16) and of the platform UI on top.
export type Box = {x: number; y: number; w: number; h: number};
export const boxFor = (portrait: boolean): Box => (portrait ? {x: 90, y: 250, w: 900, h: 1100} : {x: 150, y: 96, w: 1620, h: 700});
