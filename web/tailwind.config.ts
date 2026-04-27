import type { Config } from 'tailwindcss'

export default {
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
    // Tremor v3 — its compiled JS uses Tailwind classes that need to be
    // included in our scan or they'll be purged.
    './node_modules/@tremor/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        // Tremor token palette (per Tremor v3 install docs).
        tremor: {
          brand: {
            faint:    '#eef2ff', // indigo-50
            muted:    '#c7d2fe', // indigo-200
            subtle:   '#818cf8', // indigo-400
            DEFAULT:  '#6366f1', // indigo-500
            emphasis: '#4338ca', // indigo-700
            inverted: '#ffffff',
          },
          background: {
            muted:    '#f9fafb', // gray-50
            subtle:   '#f3f4f6', // gray-100
            DEFAULT:  '#ffffff',
            emphasis: '#374151', // gray-700
          },
          border: {
            DEFAULT:  '#e5e7eb', // gray-200
          },
          ring: {
            DEFAULT:  '#e5e7eb', // gray-200
          },
          content: {
            subtle:    '#9ca3af', // gray-400
            DEFAULT:   '#6b7280', // gray-500
            emphasis:  '#374151', // gray-700
            strong:    '#111827', // gray-900
            inverted:  '#ffffff',
          },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(circle, var(--tw-gradient-stops))',
      },
      keyframes: {
        'pulse-ring': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(99, 102, 241, 0.55)' },
          '50%':      { boxShadow: '0 0 0 6px rgba(99, 102, 241, 0)' },
        },
      },
      animation: {
        'pulse-ring': 'pulse-ring 1.8s ease-out infinite',
      },
      boxShadow: {
        // Tremor expects these
        'tremor-input':         '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        'tremor-card':          '0 1px 3px 0 rgb(0 0 0 / 0.07), 0 1px 2px -1px rgb(0 0 0 / 0.04)',
        'tremor-dropdown':      '0 4px 6px -1px rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.06)',
      },
      borderRadius: {
        'tremor-small':   '0.375rem',
        'tremor-default': '0.5rem',
        'tremor-full':    '9999px',
      },
      fontSize: {
        'tremor-label':   ['0.75rem', { lineHeight: '1rem' }],
        'tremor-default': ['0.875rem', { lineHeight: '1.25rem' }],
        'tremor-title':   ['1.125rem', { lineHeight: '1.75rem' }],
        'tremor-metric':  ['1.875rem', { lineHeight: '2.25rem' }],
      },
    },
  },
  // Tremor needs these utility variants safelisted (per its docs).
  safelist: [
    {
      pattern: /^(bg|text|border|ring|fill|stroke)-(indigo|emerald|red|amber|sky|violet|fuchsia|cyan|orange|lime|rose)-(50|100|200|300|400|500|600|700|800|900)$/,
      variants: ['hover', 'ui-selected'],
    },
  ],
  plugins: [],
} satisfies Config
