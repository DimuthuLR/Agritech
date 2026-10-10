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

        'surface':             'rgb(var(--surface) / <alpha-value>)',
        'surface-hover':       'rgb(var(--surface-hover) / <alpha-value>)',
        'surface-active':      'rgb(var(--surface-active) / <alpha-value>)',
        'surface-border':      'rgb(var(--surface-border) / <alpha-value>)',
        'surface-text':        'rgb(var(--surface-text) / <alpha-value>)',
        'surface-text-muted':  'rgb(var(--surface-text-muted) / <alpha-value>)',
        'surface-accent':      'rgb(var(--surface-accent) / <alpha-value>)',
      },
      backgroundImage: {
        'app-gradient':
          'radial-gradient(circle at 30% 0%, rgba(255, 202, 96, 0.45), transparent 55%), radial-gradient(circle at 100% 100%, rgba(74, 143, 96, 0.16), transparent 60%)',
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