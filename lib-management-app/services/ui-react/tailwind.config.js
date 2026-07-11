/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Photon brand — signature orange primary
        primary: {
          50:  '#FFF3EC',
          100: '#FFE0C4',
          200: '#FFC89A',
          300: '#FFAD70',
          400: '#FF8C40',
          500: '#F56200',
          600: '#E05500',
          700: '#CC4C00',
          800: '#A33C00',
          900: '#7A2D00',
        },
        // Photon deep navy sidebar
        sidebar: {
          bg:         '#0D1B2E',
          hover:      '#162438',
          active:     '#F56200',
          text:       '#94A3B8',
          activeText: '#FFFFFF',
        },
        status: {
          mandatory:   '#ef4444',
          recommended: '#f59e0b',
          ok:          '#10b981',
          deprecated:  '#6b7280',
          pending:     '#8b5cf6',
        },
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
      boxShadow: {
        card:   '0 1px 3px 0 rgb(0 0 0 / 0.08), 0 1px 2px -1px rgb(0 0 0 / 0.06)',
        'card-hover': '0 4px 12px 0 rgb(0 0 0 / 0.12)',
        orange: '0 4px 14px 0 rgb(245 98 0 / 0.35)',
      },
    },
  },
  plugins: [],
}
