/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['selector', '[data-theme="dark"]'],
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
            colors: {
        'bg':          'rgb(var(--bg) / <alpha-value>)',
        'card':        'rgb(var(--card) / <alpha-value>)',
        'card-hover':  'rgb(var(--card-hover) / <alpha-value>)',
        'border':      'rgb(var(--border) / <alpha-value>)',

        'text':        'rgb(var(--text) / <alpha-value>)',
        'muted':       'rgb(var(--text-muted) / <alpha-value>)',
        'invert':      'rgb(var(--text-invert) / <alpha-value>)',

        'accent':      'rgb(var(--accent) / <alpha-value>)',
        'accent-soft': 'rgb(var(--accent-soft) / <alpha-value>)',
        'water':       'rgb(var(--water) / <alpha-value>)',
        'success':     'rgb(var(--success) / <alpha-value>)',
        'warning':     'rgb(var(--warning) / <alpha-value>)',
        'danger':      'rgb(var(--danger) / <alpha-value>)',
      },
      borderRadius: {
        DEFAULT: 'var(--radius)',
        sm:      'var(--radius-sm)',
        lg:      'calc(var(--radius) + 4px)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}