import type {ThemeName} from '../types';

export type Theme = {base: string; glow?: string; glowAt: string; glow2?: string; glow2At?: string; ink: string; mute: string; accent: string; line: string; dark: boolean};

// Canvases behind the evidence panel in studio style. Light ones are off-white with one
// pastel glow in a corner, dark ones are charcoal or navy with a colored glow.
export const THEMES: Record<ThemeName, Theme> = {
  light: {base: '#f4f3ef', glowAt: '100% 0%', ink: '#15171b', mute: '#5d636b', accent: '#2f5bd3', line: 'rgba(0,0,0,.05)', dark: false},
  blush: {base: '#f4f3ef', glow: '#f6b9d0', glowAt: '100% 0%', ink: '#15171b', mute: '#5d636b', accent: '#d63a6e', line: 'rgba(0,0,0,.05)', dark: false},
  lime: {base: '#f4f3ef', glow: '#d6f59a', glowAt: '0% 100%', ink: '#15171b', mute: '#5d636b', accent: '#4c8a12', line: 'rgba(0,0,0,.05)', dark: false},
  periwinkle: {base: '#f4f3ef', glow: '#b3c2f7', glowAt: '100% 50%', ink: '#15171b', mute: '#5d636b', accent: '#2f5bd3', line: 'rgba(0,0,0,.05)', dark: false},
  dark: {base: '#16181c', glowAt: '100% 100%', ink: '#f5f5f2', mute: '#9aa0a8', accent: '#f2a93b', line: 'rgba(255,255,255,.04)', dark: true},
  crimson: {base: '#16181c', glow: '#7d1233', glowAt: '100% 100%', ink: '#f5f5f2', mute: '#a3a3ab', accent: '#ff3d6e', line: 'rgba(255,255,255,.04)', dark: true},
  midnight: {base: '#0d1830', glow: '#2b4d94', glowAt: '0% 0%', ink: '#f5f5f2', mute: '#a8b3c7', accent: '#f2a93b', line: 'rgba(255,255,255,.05)', dark: true},
  // board style: near-black navy, teal glow top left, violet glow bottom right
  // board split layout (quiz tips): the cream card canvas, coral accent
  paper: {base: '#f7f5ee', glowAt: '50% 50%', ink: '#17191d', mute: '#6a6f77', accent: '#d4523f', line: 'rgba(0,0,0,.03)', dark: false},
  glow: {base: '#0a0f1d', glow: '#0f5e5a', glowAt: '8% 0%', glow2: '#3b2470', glow2At: '100% 100%', ink: '#f2f5f8', mute: '#93a1b5', accent: '#2dd4bf', line: 'rgba(255,255,255,.035)', dark: true},
};

export const themeOf = (name?: ThemeName) => THEMES[name ?? 'light'] ?? THEMES.light;

export const canvasCss = (t: Theme) => {
  const grid = `repeating-linear-gradient(0deg, ${t.line} 0 1px, transparent 1px 48px), repeating-linear-gradient(90deg, ${t.line} 0 1px, transparent 1px 48px)`;
  const glow = t.glow ? `radial-gradient(circle at ${t.glowAt}, ${t.glow} 0%, ${t.glow}00 60%), ` : '';
  const glow2 = t.glow2 ? `radial-gradient(circle at ${t.glow2At ?? '100% 100%'}, ${t.glow2} 0%, ${t.glow2}00 55%), ` : '';
  return `${glow}${glow2}${grid}, ${t.base}`;
};

export const display = "'SF Pro Display', 'Helvetica Neue', Arial, sans-serif";
