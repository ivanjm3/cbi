import type { Config } from 'tailwindcss'

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Background layers
        'bg-primary': '#f8f9fa',
        'bg-secondary': '#ffffff',
        'bg-sidebar': '#1e293b',
        'bg-input': '#f1f5f9',

        // Text hierarchy
        'text-primary': '#1e293b',
        'text-secondary': '#475569',
        'text-muted': '#94a3b8',
        'text-inverse': '#f8fafc',

        // Accent colors
        'accent-primary': '#3b82f6',
        'accent-hover': '#2563eb',
        'accent-subtle': '#eff6ff',
        'accent-teal': '#0d9488',

        // Borders
        'border-default': '#e2e8f0',
        'border-subtle': '#f1f5f9',

        // Status colors
        'status-error': '#dc2626',
        'status-success': '#059669',
        'status-warning': '#d97706',

        // Chat-specific
        'bubble-user': '#3b82f6',
        'bubble-system': '#ffffff',
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06)',
        'card-hover': '0 4px 6px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.06)',
        'panel': '0 2px 8px rgba(0, 0, 0, 0.06)',
        'sidebar': '2px 0 8px rgba(0, 0, 0, 0.04)',
      },
      fontFamily: {
        'sans': ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        'mono': ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        'xs': '0.75rem',
        'sm': '0.8125rem',
        'base': '0.875rem',
        'lg': '1rem',
        'xl': '1.25rem',
      },
      animation: {
        'fadeIn': 'fadeIn 0.3s ease-in-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
