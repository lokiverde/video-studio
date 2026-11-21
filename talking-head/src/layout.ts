export type Rect = {x: number; y: number; w: number; h: number; r: number};

export type Layout = {
  portrait: boolean;
  W: number;
  H: number;
  full: Rect;
  card: Rect;
  // panel is authored at panelW wide and scaled to fit
  panel: {x: number; y: number; w: number; h: number; scale: number};
  // studio: a section with full:true drops Tony's card and uses this whole area
  fullPanel: {x: number; y: number; w: number; h: number};
  caption: {card: React.CSSProperties; full: React.CSSProperties; cardFont: number; fullFont: number; cardMax: number; fullMax: number};
  title: {font: number; pad: number; gradient: string; maxW: number};
  lowerThird: React.CSSProperties;
  tag: {style: React.CSSProperties; font: number; dot: number};
  counter: React.CSSProperties;
  disclaimerTop: number;
};

export const PANEL_W = 1060;

export const LANDSCAPE: Layout = {
  portrait: false,
  W: 1920,
  H: 1080,
  full: {x: 0, y: 0, w: 1920, h: 1080, r: 0},
  card: {x: 1230, y: 90, w: 600, h: 840, r: 36},
  panel: {x: 90, y: 90, w: PANEL_W, h: 900, scale: 1},
  fullPanel: {x: 200, y: 90, w: 1520, h: 900},
  caption: {
    card: {left: 1180, width: 700, bottom: 56},
    full: {left: 0, width: 1920, bottom: 70},
    cardFont: 30,
    fullFont: 44,
    cardMax: 640,
    fullMax: 1400,
  },
  title: {font: 112, pad: 110, maxW: 1100, gradient: 'linear-gradient(90deg, rgba(15,42,67,.88) 0%, rgba(15,42,67,.55) 55%, rgba(15,42,67,0) 100%)'},
  lowerThird: {left: 90, bottom: 190},
  tag: {style: {left: 90, top: 80}, font: 56, dot: 130},
  counter: {right: 110, top: 300},
  disclaimerTop: 60,
};

// 9:16. Top ~220px and bottom ~340px are covered by platform UI, keep content inside.
export const PORTRAIT: Layout = {
  portrait: true,
  W: 1080,
  H: 1920,
  full: {x: 0, y: 0, w: 1080, h: 1920, r: 0},
  // blockier than the full-width strip: head and shoulders, same feel as the 16:9 card
  card: {x: 200, y: 1005, w: 680, h: 570, r: 36},
  panel: {x: 60, y: 230, w: 960, h: 760, scale: 960 / PANEL_W},
  fullPanel: {x: 60, y: 300, w: 960, h: 1200},
  caption: {
    card: {left: 0, width: 1080, top: 1596},
    full: {left: 0, width: 1080, bottom: 420},
    cardFont: 38,
    fullFont: 46,
    cardMax: 940,
    fullMax: 940,
  },
  title: {font: 92, pad: 70, maxW: 940, gradient: 'linear-gradient(180deg, rgba(15,42,67,.25) 0%, rgba(15,42,67,.82) 45%, rgba(15,42,67,.82) 70%, rgba(15,42,67,.3) 100%)'},
  lowerThird: {left: 60, bottom: 560},
  tag: {style: {left: 60, top: 250}, font: 46, dot: 110},
  counter: {right: 70, top: 520},
  disclaimerTop: 250,
};

// Studio style (Wes McDowell format): a bigger, rimless card that can sit on either side
export const STUDIO_LANDSCAPE: Layout = {
  ...LANDSCAPE,
  card: {x: 1110, y: 80, w: 730, h: 920, r: 40},
  panel: {x: 110, y: 90, w: 900, h: 900, scale: 900 / PANEL_W},
  caption: {...LANDSCAPE.caption, card: {left: 1110, width: 730, bottom: 110}},
};

export const STUDIO_PORTRAIT: Layout = {...PORTRAIT, card: {x: 160, y: 1000, w: 760, h: 600, r: 40}};

// Mirror a rect across the vertical center line, used when a section puts Tony on the left
export const mirrorX = <T extends {x: number; w: number}>(r: T, W: number): T => ({...r, x: W - r.x - r.w});
