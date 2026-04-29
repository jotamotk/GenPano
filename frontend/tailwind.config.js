/** @type {import('tailwindcss').Config} */
/*
 * GENPANO Tailwind theme — kept in lockstep with /src/index.css CSS variables.
 * ─────────────────────────────────────────────────────────────────────────
 * Rules of thumb:
 *   - For single-source-of-truth colors, use the `var(--color-*)` references
 *     below so both CSS and Tailwind pull from the same value.
 *   - For semantic named scales (accent.{50..900}, sentiment.*), we hardcode
 *     since Tailwind needs static values to build utility variants.
 *   - Source: design/prototype*.html + Figma token extraction (see
 *     docs/DESIGN_TOKENS.md for rationale).
 */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        /* ── Bound to CSS variables (single source of truth) ── */
        ink:              'var(--color-text-primary)',
        'ink-secondary':  'var(--color-text-secondary)',
        'ink-muted':      'var(--color-text-muted)',
        'ink-faint':      'var(--color-text-faint)',
        'ink-body':       'var(--color-text-body)',
        'ink-body-soft':  'var(--color-text-body-soft)',
        'ink-inverse':    'var(--color-text-inverse)',

        surface:          'var(--color-bg-card)',
        'surface-page':   'var(--color-bg-page)',
        'surface-subtle': 'var(--color-bg-subtle)',
        'surface-badge':  'var(--color-bg-badge)',
        'surface-sidebar':'var(--color-bg-sidebar)',

        /* ── Accent (Figma primary purple #605BFF) ── */
        accent: {
          50:  '#F4F4FF',
          100: '#EDECFF',
          200: '#D9D7FF',
          300: '#C9C7F8',
          400: '#ACA9FF',
          500: '#605BFF',   /* brand primary */
          600: '#5450E6',
          700: '#4440C0',
          800: '#353299',
          900: '#272473',
        },

        /* Auth prototype compatibility — maps old `primary-*` classes to
           the locked GENPANO accent tokens while pages migrate to semantic
           `.t-*` components. */
        primary: {
          50:  'var(--color-accent-bg-light)',
          100: 'var(--color-accent-bg-light)',
          500: 'var(--color-primary-500)',
          600: 'var(--color-primary-600)',
          700: 'var(--color-primary-700)',
        },
        'brand-beige': 'var(--color-auth-visual-bg)',
        'auth-note': 'var(--color-auth-note-bg)',

        /* ── DEPRECATED alias — retained so legacy `bf-*` utilities in
           ProjectSettingsPage.jsx (text-bf-400, bg-bf-400, ring-bf-400,
           hover:border-bf-400) keep working. New code must use `accent-*`.
           Remove once ProjectSettingsPage is migrated. */
        bf: {
          50:  '#F4F4FF',
          100: '#EDECFF',
          200: '#D9D7FF',
          300: '#C9C7F8',
          400: '#605BFF',   /* maps to accent-500 (primary brand purple) */
          500: '#605BFF',
          600: '#5450E6',
          700: '#4440C0',
          800: '#353299',
          900: '#272473',
        },

        /* ── Chart palette (Figma dashboard line chart) ── */
        chart: {
          1: '#030229',   /* 可见度 */
          2: '#FF708B',   /* 情感 (pink) */
          3: '#3B82F6',   /* 品牌声量 (blue) */
          4: '#1E3A8A',   /* 引用率 (navy) */
          5: '#605BFF',   /* accent */
          6: '#FDB022',   /* warning amber */
          7: '#0ABB87',   /* success green */
          blue:   '#3B82F6',
          navy:   '#1E3A8A',
          pink:   '#FF708B',
          amber:  '#FDB022',
          green:  '#0ABB87',
          violet: '#605BFF',
        },

        /* ── Sentiment (Topics sentiment bar) ── */
        sentiment: {
          positive: '#FF708B',
          neutral:  '#DFE3F3',
          warning:  '#FDB022',
          brand:    '#605BFF',
          mild:     '#C9C7F8',
        },

        /* ── Semantic ── */
        success: { DEFAULT: '#0ABB87', bg: 'rgba(10,187,135,0.08)' },
        warning: { DEFAULT: '#F5A623', bg: 'rgba(245,166,35,0.08)' },
        danger:  { DEFAULT: '#DB373F', bg: 'rgba(219,55,63,0.07)' },
        info:    { DEFAULT: '#605BFF', bg: '#F0F0FF' },

        /* ── Borders ── */
        border: {
          DEFAULT: '#D0D5DD',          /* form/input */
          card:    '#F2F4F7',          /* soft card outline */
          subtle:  '#E8E8F0',
          strong:  '#C1C9D2',
        },
      },

      fontFamily: {
        /* Figma: Nunito for brand + Microsoft YaHei for Chinese UI */
        sans:    ['Nunito', 'Inter', '"Microsoft YaHei"', '"Noto Sans SC"', 'system-ui', 'sans-serif'],
        brand:   ['Nunito', 'system-ui', 'sans-serif'],
        'ui-cn': ['"Microsoft YaHei"', '"Noto Sans SC"', 'sans-serif'],
        mono:    ['"IBM Plex Mono"', 'monospace'],
      },

      fontSize: {
        /* Matches prototype / Figma text hierarchy */
        'display-1': ['3rem',     { lineHeight: '1.1',  letterSpacing: '-0.02em',  fontWeight: '700' }],
        'display-2': ['2.25rem',  { lineHeight: '1.15', letterSpacing: '-0.015em', fontWeight: '700' }],
        'display-3': ['1.875rem', { lineHeight: '1.2',  letterSpacing: '-0.015em', fontWeight: '700' }],
        'heading-1': ['1.5rem',   { lineHeight: '1.3',  letterSpacing: '-0.01em',  fontWeight: '700' }],
        'heading-2': ['1.25rem',  { lineHeight: '1.35', letterSpacing: '-0.005em', fontWeight: '600' }],
        'heading-3': ['1.125rem', { lineHeight: '1.4',                             fontWeight: '600' }],
        'body':      ['1rem',     { lineHeight: '1.5',                             fontWeight: '400' }],
        'body-sm':   ['0.875rem', { lineHeight: '1.5',                             fontWeight: '400' }],
        'body-xs':   ['0.75rem',  { lineHeight: '1.4',                             fontWeight: '400' }],
        'data-xl':   ['2.25rem',  { lineHeight: '1',    letterSpacing: '-0.02em',  fontWeight: '700' }],
        'data-lg':   ['1.5rem',   { lineHeight: '1',    letterSpacing: '-0.015em', fontWeight: '700' }],
      },

      borderRadius: {
        'input':   '6px',
        'btn':     '6px',
        'btn-lg':  '8px',
        'badge':   '6px',
        'card':    '12px',
        'card-lg': '16px',
        'banner':  '24px',
        'pill':    '9999px',
      },

      boxShadow: {
        'card':       '0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03)',
        'card-hover': '0 8px 24px rgba(50,50,93,0.08), 0 2px 6px rgba(0,0,0,0.04)',
        'elevated':   '0 25px 50px rgba(50,50,93,0.25)',
        'btn':        '0 1px 3px rgba(0,0,0,0.10), 0 1px 2px rgba(0,0,0,0.10)',
        'btn-hover':  '0 4px 8px rgba(50,50,93,0.12), 0 1px 3px rgba(0,0,0,0.06)',
        'input':      '0 1px 2px rgba(16,24,40,0.05)',
        'header':     '0 1px 3px rgba(50,50,93,0.06)',
      },

      backgroundImage: {
        'gradient-accent':  'linear-gradient(135deg, #605BFF 0%, #8B5CF6 100%)',
        'gradient-warm':    'linear-gradient(135deg, #FFC7D4, #FFE0C7)',
        'gradient-nav-active': 'linear-gradient(90deg, rgba(172,169,255,1) 0%, rgba(172,169,255,0) 24%)',
      },

      maxWidth: {
        'container': '1204px',
      },

      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
        '30': '7.5rem',
        '34': '8.5rem',
        '38': '9.5rem',
      },

      animation: {
        'fade-up': 'fadeUp 0.6s cubic-bezier(0.22,1,0.36,1) forwards',
        'fade-in': 'fadeIn 0.5s ease forwards',
        'slide-in':'slideIn 0.5s cubic-bezier(0.22,1,0.36,1) forwards',
      },
      keyframes: {
        fadeUp: {
          '0%':   { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideIn: {
          '0%':   { opacity: '0', transform: 'translateX(-16px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
    },
  },
  plugins: [],
}
