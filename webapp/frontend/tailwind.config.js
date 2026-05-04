/**
 * Tailwind config — single source of truth for design tokens.
 *
 * Tokens align with `src/theme/algoTheme.js` so legacy MUI components and new
 * Tailwind components render the same colors during the migration.
 *
 * Per FRONTEND_DESIGN_SYSTEM.md / DESIGN_REDESIGN_PLAN.md:
 *   - Light theme default, dark via `class="dark"` on <html> or <body>
 *   - Inter for UI, IBM Plex Mono for numerics
 *   - 4px spacing scale (Tailwind defaults already match)
 *   - Hairline borders, subtle shadows, no radius > 12px on data UI
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // ── Surfaces ──────────────────────────────────────────────────
        bg: {
          DEFAULT: '#FAFAF7',   // warm white page bg
          elev: '#FFFFFF',      // cards / drawer / header
          alt: '#F5F5F0',       // alt rows / hover surface
          lift: '#EDEDE6',      // pressed state
        },
        // ── Borders ───────────────────────────────────────────────────
        border: {
          DEFAULT: '#E5E4DC',
          strong: '#C9C8BE',
          light: '#EDECE5',
        },
        // ── Text ──────────────────────────────────────────────────────
        ink: {
          strong: '#1A1A1A',    // headlines
          DEFAULT: '#2C2C28',   // body
          muted: '#6A6A65',     // labels
          faint: '#9A9A95',     // captions
          inverted: '#FAFAF7',  // text on dark surfaces
        },
        // ── Brand (deep verdant) ──────────────────────────────────────
        brand: {
          DEFAULT: '#0E5C3A',
          hover: '#08402A',
          soft: '#E6F2EC',
          tint: '#F2F8F4',
          glow: '#2DBC83',
        },
        // ── Semantic ──────────────────────────────────────────────────
        bull: {
          DEFAULT: '#1F9956',
          deep: '#0E5C3A',
          soft: '#E0F4E8',
        },
        bear: {
          DEFAULT: '#E0392B',
          deep: '#B22A1E',
          soft: '#FBE0DD',
        },
        warn: {
          DEFAULT: '#E08F1B',
          deep: '#B07015',
          soft: '#FCEFD3',
        },
        info: {
          DEFAULT: '#4A90E2',
          soft: '#E3F0FB',
        },
        // ── Multi-accent palette (for chips/categorization) ───────────
        coral: { DEFAULT: '#FF6B47', soft: '#FFE5DD' },
        honey: { DEFAULT: '#F4B942', soft: '#FDF1D9' },
        berry: { DEFAULT: '#C2185B', soft: '#FCE4EC' },
        sky: { DEFAULT: '#4A90E2', soft: '#E3F0FB' },
        plum: { DEFAULT: '#6B5B95', soft: '#EFEBF7' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', '"SF Mono"', 'Menlo', 'Consolas', 'monospace'],
        display: ['Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        // Pair: [size, lineHeight] — line heights set explicitly
        '2xs': ['10px', { lineHeight: '14px', letterSpacing: '0.05em', fontWeight: '600' }],
        xs:   ['12px', { lineHeight: '16px', fontWeight: '500' }],
        sm:   ['14px', { lineHeight: '20px' }],
        base: ['16px', { lineHeight: '22px' }],
        lg:   ['18px', { lineHeight: '24px', letterSpacing: '-0.005em' }],
        xl:   ['24px', { lineHeight: '28px', letterSpacing: '-0.01em' }],
        '2xl': ['32px', { lineHeight: '36px', letterSpacing: '-0.02em' }],
        '3xl': ['40px', { lineHeight: '44px', letterSpacing: '-0.02em' }],
        '4xl': ['52px', { lineHeight: '56px', letterSpacing: '-0.025em' }],
      },
      fontWeight: {
        normal: '400',
        medium: '500',
        semibold: '600',
        bold: '700',
        black: '800',
      },
      borderRadius: {
        DEFAULT: '8px',
        none: '0',
        xs: '2px',
        sm: '4px',
        md: '8px',
        lg: '12px',  // max for data UI
        xl: '16px',  // overlays only
        full: '9999px',
      },
      boxShadow: {
        // Hairline-style shadows; never used on data cards (cards use border)
        'sm': '0 1px 2px rgba(15,26,17,0.04)',
        'DEFAULT': '0 1px 2px rgba(15,26,17,0.04), 0 2px 6px rgba(15,26,17,0.04)',
        'md': '0 2px 4px rgba(15,26,17,0.04), 0 8px 20px rgba(15,26,17,0.07)',
        'lg': '0 8px 16px rgba(15,26,17,0.06), 0 20px 40px rgba(15,26,17,0.10)',
        'glow': '0 8px 32px rgba(14,92,58,0.18)',
        'none': 'none',
      },
      spacing: {
        // Default Tailwind 4px scale extends with a couple useful adds
        18: '4.5rem',  // 72px — common nav width fraction
        22: '5.5rem',
        '60': '15rem', // 240px — drawer width
        '70': '17.5rem',
        '76': '19rem',
      },
      transitionDuration: {
        fast: '100ms',
        DEFAULT: '150ms',
        slow: '250ms',
      },
      transitionTimingFunction: {
        DEFAULT: 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      maxWidth: {
        'page': '1600px',  // max page content width
      },
    },
  },
  plugins: [
    // Tabular figures + slashed zero utility
    function ({ addUtilities }) {
      addUtilities({
        '.tnum': {
          fontFeatureSettings: '"tnum", "cv11"',
          fontVariantNumeric: 'tabular-nums slashed-zero',
        },
        '.no-tnum': {
          fontFeatureSettings: 'normal',
          fontVariantNumeric: 'normal',
        },
      });
    },
  ],
};
