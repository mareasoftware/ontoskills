/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        'bg-primary': '#0d0d14',
        'bg-secondary': '#1a1a2e',
        'bg-tertiary': '#16213e',
        'text-primary': '#f0f0f5',
        'text-muted': '#8b8ba3',
        'accent-cyan': '#6dc9ee',
        'accent-purple': '#9763e1',
        'accent-mint': '#abf9cc',
        'accent-aqua': '#92eff4',
        'border': '#2a2a3e',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      backgroundImage: {
        'gradient-text': 'linear-gradient(135deg, #6dc9ee, #9763e1)',
        'gradient-logo': 'linear-gradient(135deg, #92eff4, #abf9cc)',
      },
    },
  },
  plugins: [],
};
