export type Part = string | {hl: string; at: number};

export type Block =
  | {type: 'statute'; cite: string; heading?: string; source?: string; parts: Part[]}
  | {type: 'note'; text: string; at: number; color?: string}
  | {type: 'quote'; text: string; at: number; xAt?: number}
  | {type: 'stat'; label: string; value: string; at: number}
  | {type: 'strike'; value: string; note: string; at: number; noteAt: number}
  | {type: 'list'; items: Array<{name: string; who?: string; at: number}>}
  | {type: 'bar'; label?: string; at: number; dangerAt?: number; noteAt?: number; note?: string}
  | {type: 'formula'; terms: string[]; caption?: string; at: number}
  | {type: 'traffic'; items: Array<{color: 'green' | 'yellow' | 'red'; title: string; body?: string; at: number}>}
  | {type: 'cta'; kicker?: string; headline: string; at: number}
  // studio style blocks (Wes McDowell format)
  | {type: 'headline'; text: string; at: number; sub?: string}
  | {type: 'bigstat'; value: string; label?: string; source?: string; at: number; icons?: {kind: IconName; of: number; filled: number; at?: number}}
  | {type: 'steps'; title?: string; items: Array<{text: string; sub?: string; icon?: IconName; at: number}>}
  | {type: 'bars'; source?: string; items: Array<{label: string; value: number; at: number}>}
  | {type: 'screen'; file: string; at: number; caption?: string}
  // news style: outlet on top (logo file or its name), the quote typing in below
  | {type: 'pullquote'; text: string; at: number; source?: string; logo?: string}
  // board style: a real screenshot (comment, post, page), the quoted line highlighted, slow push in.
  // highlight is [x, y, w, h] as fractions of the image. Handles are blurred in the file itself.
  // lines: one box per line of the quote (drawn, swept in order); highlight is the whole quote (push target)
  | {type: 'receipt'; file: string; at: number; highlight?: [number, number, number, number]; lines?: Array<[number, number, number, number]>; source?: string};

export type IconName = 'person' | 'play' | 'check' | 'dollar' | 'home' | 'doc' | 'chart' | 'key' | 'calendar' | 'shield' | 'search' | 'phone' | 'star' | 'clock' | 'chat';

export type ThemeName = 'light' | 'blush' | 'lime' | 'periwinkle' | 'dark' | 'crimson' | 'midnight' | 'glow' | 'paper';

// Board style (Peverelli format): a full-screen grid, one card per item, that comes back at
// each new item and lights up the active one. Cards past `revealed` show "?".
export type Board = {
  title?: string;
  items: Array<{tag?: string; label: string; sub?: string}>;
  shows: Array<{from: number; to: number; active: number; revealed: number}>;
  // split layout: false drops the big number that sweeps across before each item
  wipe?: boolean;
};

// Kinetic phrase: one line of on-screen text over Tony, `em` gets an underline sweep
export type Phrase = {from: number; to: number; text: string; em?: string; pos?: 'bottom' | 'side'};

// News style: a line that types itself in at the top of the frame, key words in color
export type TypedColor = 'green' | 'red' | 'amber';
export type Typed = {from: number; to: number; text: string; hl?: Array<{text: string; color?: TypedColor}>; pos?: 'left' | 'right'; size?: 'big'};

// News style: a transparent PNG that pops in beside Tony
export type Sticker = {from: number; to: number; file: string; pos?: 'left' | 'right' | 'bottom-left' | 'bottom-right'; scale?: number};

export type Section = {
  tag?: {n: number; topic: string; from: number; to: number};
  evidence: [number, number];
  blocks: Block[];
  // studio and news styles only
  theme?: ThemeName;
  side?: 'left' | 'right';
  full?: boolean; // no Tony card, the panel takes the whole canvas (screens, examples)
};

export type Brand = {navy: string; ink: string; paper: string; amber: string; red: string; yellow: string; green: string; mute: string};

// Focal point (0..1 of the source frame) and zoom, so a wide or off-center shot still
// puts Tony's face where the layout expects it
export type Frame = {x: number; y: number; zoom: number};

export type LowerThird = {from: number; to: number; name: string; line: string};

// Army style: th.py sends the beats with the stills army.py drew for this cut, Tony's inset
// box (army.py's frame box) and the runs he stays in it (th_army.render_props)
export type ArmyClipWindow = {x: number; y: number; w: number; h: number; r: number; border: number};
export type ArmyBeat = {
  from: number;
  to: number;
  layout: 'full' | 'split' | 'inset' | 'graphic';
  file?: string;
  textFile?: string;
  kind?: string;
  // a split beat that plays a screen recording in the card (kind 'clip'): its window in card pixels
  clip?: string;
  start?: number;
  rate?: number;
  zoom?: number;
  focus?: [number, number];
  window?: ArmyClipWindow;
};
export type ArmyRect = {x: number; y: number; w: number; h: number; r: number; border: number};
export type ArmyProps = {
  canvas: string;
  end: string | null;
  inset: ArmyRect;
  // the main layout: graphics card beside Tony's panel, captions in the card's bottom band
  split: {card: ArmyRect; tony: ArmyRect; caption: {x: number; y: number; w: number}};
  runs: {inset: Array<[number, number]>; split: Array<[number, number]>};
  // a big number sweeps across before each trading card beside Tony
  wipes: Array<{at: number; file: string}>;
  beats: ArmyBeat[];
};

export type Job = {
  title: string;
  framing?: {full?: Frame; card?: Frame; portraitFull?: Frame; portraitCard?: Frame; split?: Frame; portraitSplit?: Frame; inset?: Frame; portraitInset?: Frame};
  source: string;
  srcEnd: number;
  cuts: Array<[number, number]>;
  brand?: Partial<Brand>;
  hook?: {from: number; to: number; broll: string[]; kicker?: string; title: string};
  // one name bar, or several (intro, then a contact bar over the closing pitch)
  lowerThird?: LowerThird | LowerThird[];
  counter?: {from: number; to: number; count: number};
  disclaimer?: {from: number; text: string};
  endCard?: {seconds: number; kicker?: string; headline: string; sub?: string};
  // Full-screen b-roll over Tony's audio, anywhere in the video. file is a still or an .mp4 in public/
  // fit 'blur' frames the whole photo over a blurred copy of itself instead of cropping it
  cutaways?: Array<{from: number; to: number; file: string; fit?: 'cover' | 'blur'}>;
  sections: Section[];
  // 'evidence' (default): white canvas, bordered card, running captions.
  // 'studio': themed gradient canvases, card swaps sides, punch-ins on every cut, kinetic phrases.
  // 'news': Tony stays full frame, typed lines and cutout stickers land beside him, photos cut in.
  // 'board': Tony full frame, full-screen glow sections and receipts, a recurring board, key-word captions.
  // 'army': the Army format on the navy canvas, Tony full frame, in the inset box or cut away to graphics.
  style?: 'evidence' | 'studio' | 'news' | 'board' | 'army';
  army?: ArmyProps;
  // board style only. 'full' (default): graphics take the whole frame and hide Tony.
  // 'split' (the quiz tips look): Tony stays on the right third, graphics in a light card on the left.
  layout?: 'full' | 'split';
  board?: Board;
  // board style: words colored gold in the captions wherever they appear
  keywords?: string[];
  typed?: Typed[];
  stickers?: Sticker[];
  punch?: boolean;
  punchZoom?: number;
  punches?: number[];
  phrases?: Phrase[];
  // 'auto': studio shows phrases only in 16:9 and running captions in 9:16
  captionMode?: 'auto' | 'full' | 'phrases' | 'off';
  captions?: Array<{s: number; e: number; t: string}>;
};

export const DEFAULT_BRAND: Brand = {
  navy: '#0f2a43',
  ink: '#16202b',
  paper: '#fbfaf7',
  amber: '#f2a93b',
  red: '#d6453d',
  yellow: '#e9b93a',
  green: '#3d9a5f',
  mute: '#6b7785',
};

// Studio, news and board share the studio layout, punch-ins and full-screen sections
export const isStudio = (job: Job) => job.style === 'studio' || job.style === 'news' || job.style === 'board';
