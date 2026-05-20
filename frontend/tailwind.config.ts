import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        navy: '#0A0F1E',
        'navy-card': '#111827',
        'navy-border': '#1F2937',
        gold: '#F59E0B',
        'gold-muted': '#92400E',
        crimson: '#DC2626',
        emerald: '#10B981',
        'blue-agent': '#3B82F6',
        'green-agent': '#22C55E',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;
