import type {IconName} from '../types';

// Simple line icons, 24x24 grid, drawn with the current color
const PATHS: Record<IconName, string> = {
  person: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5',
  play: 'M3 6a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3zM10 8.5v7l6-3.5z',
  check: 'M4 12.5l5 5L20 6.5',
  dollar: 'M12 2v20M17 6.5c-1-1.5-3-2-5-2-2.8 0-4.5 1.4-4.5 3.4 0 4.6 9.5 2.5 9.5 7.4 0 2-1.9 3.6-5 3.6-2.3 0-4.2-.8-5.2-2.4',
  home: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z',
  doc: 'M6 2h8l5 5v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1zM14 2v5h5M8 13h8M8 17h6',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  key: 'M8 15a5 5 0 1 1 3.9-8.1L21 16v4h-4v-2h-2v-2h-2.1A5 5 0 0 1 8 15zM7 11h.01',
  calendar: 'M4 5h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM3 10h18M8 3v4M16 3v4',
  shield: 'M12 2l8 3v6c0 5-3.4 9.3-8 11-4.6-1.7-8-6-8-11V5z',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-5-5',
  phone: 'M5 3h4l2 5-2.5 1.5a11 11 0 0 0 6 6L16 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 5a2 2 0 0 1 2-2z',
  star: 'M12 3l2.8 5.8 6.2.9-4.5 4.4 1.1 6.2L12 17.4 6.4 20.3l1.1-6.2L3 9.7l6.2-.9z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  chat: 'M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-5 4v-4H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z',
};

export const Icon = ({name, size, color, filled = false}: {name: IconName; size: number; color: string; filled?: boolean}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={filled ? color : 'none'} stroke={color} strokeWidth={filled ? 1.2 : 1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d={PATHS[name] ?? PATHS.check} />
  </svg>
);
