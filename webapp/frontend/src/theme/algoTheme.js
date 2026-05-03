/**
 * Bullseye Trading — Unified Design System
 *
 * Hybrid light/dark theme inspired by Bloomberg Terminal, Koyfin, Stripe.
 * Default: clean light palette for max data clarity.
 * Optional: dark mode toggle for low-light/long-session use.
 *
 * Each page builds with these tokens — purpose-designed, not template-driven.
 * Mobile-responsive from the foundation.
 *
 * Usage:
 *   import { C, F, S, comp } from '@/theme/algoTheme';
 *   <Box sx={{ bgcolor: C.card, color: C.text }} />
 */

// ============================================================================
// THEME MODE — controlled via localStorage 'algo-theme' = 'light' | 'dark'
// ============================================================================
const getMode = () => {
  if (typeof window === 'undefined') return 'light';
  return localStorage.getItem('algo-theme') || 'light';
};

const setMode = (mode) => {
  if (typeof window !== 'undefined') {
    localStorage.setItem('algo-theme', mode);
    window.dispatchEvent(new Event('algo-theme-change'));
  }
};

// ============================================================================
// COLOR TOKENS — light is default, dark is opt-in
// ============================================================================
const lightTokens = {
  // === SURFACES — warm, premium, captivating (WhatsForLunch-inspired) ===
  // Slight warm tint instead of cold gray — feels more inviting for hours of use
  bg:        '#FAFAF7',   // warm white page bg
  bgElev:    '#FFFFFF',   // sidebar/header
  card:      '#FFFFFF',
  cardAlt:   '#F7F7F2',   // warm alt rows
  cardLift:  '#F0EFE8',

  // === BORDERS ===
  border:        '#E5E4DC',
  borderLight:   '#EDECE5',
  borderStrong:  '#C9C8BE',

  // === TEXT (warm dark, not pure black — premium feel) ===
  textBright: '#1A1A1A',
  text:       '#2C2C28',
  textDim:    '#6A6A65',
  textFaint:  '#9A9A95',

  // === BRAND — deep verdant green (premium, financial gravity + life) ===
  brand:     '#0E5C3A',   // deep verdant — same as WhatsForLunch
  brandDark: '#08402A',
  brandSoft: '#E6F2EC',
  brandTint: '#F2F8F4',
  brandGlow: '#2DBC83',

  // === FINANCIAL SEMANTIC ===
  bull:      '#1F9956',   // confident green
  bullDeep:  '#0E5C3A',
  bullSoft:  '#E0F4E8',
  bear:      '#E0392B',   // urgent but not screaming
  bearDeep:  '#B22A1E',
  bearSoft:  '#FBE0DD',
  warn:      '#E08F1B',   // honey amber — warm caution
  warnDeep:  '#B07015',
  warnSoft:  '#FCEFD3',

  // === CAPTIVATING ACCENTS (multi-color palette for status/mood) ===
  coral:     '#FF6B47',   // energy, urgency, attention
  coralSoft: '#FFE5DD',
  honey:     '#F4B942',   // warmth, joy, achievements
  honeySoft: '#FDF1D9',
  berry:     '#C2185B',   // premium, special, ranked highly
  berrySoft: '#FCE4EC',
  sky:       '#4A90E2',   // info, calm, neutral data
  skySoft:   '#E3F0FB',
  plum:      '#6B5B95',   // premium tier, paid features
  plumSoft:  '#EFEBF7',

  // Aliases for backward compatibility
  blue:      '#4A90E2',   // = sky
  blueSoft:  '#E3F0FB',
  purple:    '#6B5B95',   // = plum
  purpleSoft: '#EFEBF7',
  cyan:      '#39C5CF',
  pink:      '#C2185B',
  amber:     '#E08F1B',
  amberSoft: '#FCEFD3',

  // === SHADOWS — softer, layered, warm ===
  shadow1:   '0 1px 2px rgba(15,26,17,0.04), 0 2px 6px rgba(15,26,17,0.04)',
  shadow2:   '0 2px 4px rgba(15,26,17,0.04), 0 8px 20px rgba(15,26,17,0.07)',
  shadow3:   '0 8px 16px rgba(15,26,17,0.06), 0 20px 40px rgba(15,26,17,0.10)',
  shadowGlow: '0 8px 32px rgba(14,92,58,0.18)',  // brand-tinted glow
  shadowCoral: '0 6px 20px rgba(255,107,71,0.20)',

  white:     '#ffffff',
  black:     '#000000',
  transparent: 'transparent',
};

const darkTokens = {
  bg:        '#0d1117',
  bgElev:    '#161b22',
  card:      '#21262d',
  cardAlt:   '#1c232c',
  cardLift:  '#2d333b',

  border:    '#30363d',
  borderLight: '#21262d',
  borderStrong: '#484f58',

  textBright: '#f0f6fc',
  text:       '#c9d1d9',
  textDim:    '#8b949e',
  textFaint:  '#6e7681',

  brand:     '#3fb950',
  brandDark: '#238636',
  brandSoft: '#0d2818',

  bull:      '#3fb950',
  bullDeep:  '#1a7f37',
  bullSoft:  '#0c2818',
  bear:      '#f85149',
  bearDeep:  '#cf222e',
  bearSoft:  '#3a1414',
  warn:      '#d29922',
  warnSoft:  '#3a2a00',

  blue:      '#388bfd',
  blueSoft:  '#0c2d6b',
  purple:    '#a371f7',
  purpleSoft: '#2c1c5b',
  cyan:      '#39c5cf',
  pink:      '#db61a2',
  amber:     '#fb950c',
  amberSoft: '#3a1d00',

  shadow1:   'none',
  shadow2:   'none',
  shadow3:   'none',

  white:     '#ffffff',
  black:     '#000000',
  transparent: 'transparent',
};

// Active palette — dynamically switches based on localStorage
let _mode = getMode();
let _tokens = _mode === 'dark' ? darkTokens : lightTokens;

// Listen for theme changes
if (typeof window !== 'undefined') {
  window.addEventListener('algo-theme-change', () => {
    _mode = getMode();
    _tokens = _mode === 'dark' ? darkTokens : lightTokens;
  });
}

// Expose tokens via Proxy so consumers always read live values
export const C = new Proxy({}, {
  get: (target, prop) => _tokens[prop],
});

export const isDarkMode = () => _mode === 'dark';
export const setThemeMode = setMode;
export const getCurrentMode = () => _mode;

// ============================================================================
// HELPER COLORS
// ============================================================================
export const tierColor = (name) => ({
  confirmed_uptrend: _tokens.bull,
  healthy_uptrend:   _tokens.brand,
  pressure:          _tokens.warn,
  caution:           _tokens.amber,
  correction:        _tokens.bear,
}[name] || _tokens.textDim);

export const gradeColor = (g) => ({
  'A+': _tokens.bull,
  'A':  _tokens.bullDeep,
  'B':  _tokens.blue,
  'C':  _tokens.warn,
  'D':  _tokens.amber,
  'F':  _tokens.bear,
}[g] || _tokens.textDim);

export const severityColor = (s) => ({
  info:     _tokens.blue,
  warn:     _tokens.warn,
  warning:  _tokens.warn,
  error:    _tokens.bear,
  critical: _tokens.bearDeep,
  ok:       _tokens.bull,
  success:  _tokens.bull,
  stale:    _tokens.warn,
  empty:    _tokens.bear,
}[s] || _tokens.textDim);

// ============================================================================
// TYPOGRAPHY — Inter for body, JetBrains Mono for numbers
// ============================================================================
export const F = {
  body: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  mono: '"JetBrains Mono", "Fira Code", "SF Mono", Consolas, monospace',
  display: '"Inter", -apple-system, BlinkMacSystemFont, sans-serif',

  xxs:  '0.65rem',
  xs:   '0.7rem',
  sm:   '0.8125rem',
  base: '0.875rem',
  md:   '0.9375rem',
  lg:   '1.125rem',
  xl:   '1.5rem',
  xxl:  '2rem',
  xxxl: '2.5rem',
  hero: '3.25rem',

  weight: {
    regular: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
    black: 800,
  },

  overline: {
    fontSize: '0.7rem',
    letterSpacing: '0.06em',
    fontWeight: 600,
    textTransform: 'uppercase',
  },
};

// ============================================================================
// SPACING & LAYOUT
// ============================================================================
export const S = {
  xs: 0.5, sm: 1, md: 2, lg: 3, xl: 4, xxl: 6,

  navWidth: 232,
  navWidthCollapsed: 60,
  headerHeight: 56,
  footerHeight: 32,

  radiusSm: 4,
  radius:   8,
  radiusLg: 12,
  radiusXl: 16,

  // Responsive breakpoints (matches MUI but documented)
  bp: {
    xs: 0,    // mobile
    sm: 600,  // tablet
    md: 900,  // small desktop
    lg: 1200, // desktop
    xl: 1536, // wide desktop
  },
};

// ============================================================================
// COMPONENT MIXINS — used by AlgoUI primitives
// ============================================================================
export const comp = {
  card: {
    bgcolor: _tokens.card,
    color: _tokens.text,
    border: `1px solid ${_tokens.border}`,
    borderRadius: 1,
    boxShadow: _mode === 'dark' ? 'none' : _tokens.shadow1,
  },

  cardLifted: {
    bgcolor: _tokens.card,
    color: _tokens.text,
    border: `1px solid ${_tokens.border}`,
    borderRadius: 1,
    boxShadow: _mode === 'dark' ? 'none' : _tokens.shadow2,
  },

  cardHeader: {
    px: 2,
    py: 1.25,
    borderBottom: `1px solid ${_tokens.borderLight}`,
    bgcolor: _tokens.cardAlt,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  thCell: {
    bgcolor: _tokens.cardAlt,
    color: _tokens.textDim,
    borderColor: _tokens.borderLight,
    fontSize: F.xxs,
    letterSpacing: '0.06em',
    fontWeight: F.weight.semibold,
    py: 1,
  },

  tdCell: {
    color: _tokens.text,
    borderColor: _tokens.borderLight,
    fontSize: F.sm,
  },

  monoCell: {
    color: _tokens.text,
    borderColor: _tokens.borderLight,
    fontFamily: F.mono,
    fontSize: F.sm,
  },

  chip: (bg, fg = 'white') => ({
    bgcolor: bg,
    color: fg,
    height: 20,
    fontSize: F.xs,
    fontWeight: F.weight.bold,
    letterSpacing: '0.04em',
  }),
};

// ============================================================================
// FORMATTERS
// ============================================================================
export const pnlColor = (n) => (n > 0 ? _tokens.bull : n < 0 ? _tokens.bear : _tokens.textDim);
export const arrowFor = (n) => (n > 0 ? '▲' : n < 0 ? '▼' : '·');

export const fmt$ = (n, decimals = 2) => {
  if (n === null || n === undefined || isNaN(n)) return '-';
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${Number(n).toFixed(decimals)}`;
};

export const fmtPct = (n, decimals = 2) => {
  if (n === null || n === undefined || isNaN(n)) return '-';
  const sign = n > 0 ? '+' : '';
  return `${sign}${Number(n).toFixed(decimals)}%`;
};

export const fmtNum = (n, decimals = 0) => {
  if (n === null || n === undefined || isNaN(n)) return '-';
  return Number(n).toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
};

export const fmtDate = (d) => {
  if (!d) return '-';
  const date = typeof d === 'string' ? new Date(d) : d;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

export const fmtTime = (d) => {
  if (!d) return '-';
  const date = typeof d === 'string' ? new Date(d) : d;
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
};

// ============================================================================
// MOBILE / RESPONSIVE HELPERS
// ============================================================================
export const responsive = {
  // Hide on small screens
  hideOnMobile: { display: { xs: 'none', sm: 'block' } },
  hideOnTablet: { display: { xs: 'none', md: 'block' } },
  showOnlyMobile: { display: { xs: 'block', sm: 'none' } },

  // Stack to column on mobile, row on desktop
  stackOnMobile: { flexDirection: { xs: 'column', md: 'row' } },

  // Padding scale by breakpoint
  pageX: { xs: 1.5, sm: 2, md: 3 },
  pageY: { xs: 1.5, sm: 2, md: 2 },
};

export default {
  C, F, S, comp, tierColor, gradeColor, severityColor, pnlColor,
  arrowFor, fmt$, fmtPct, fmtNum, fmtDate, fmtTime,
  isDarkMode, setThemeMode, getCurrentMode, responsive,
};
