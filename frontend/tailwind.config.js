/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Синій і жовтий — кольори обох прапорів
      colors: {
        blue: { DEFAULT: '#0B4A94', dark: '#083870' },
        sun: '#FFCC00',
        note: '#FFF6CC',
        ink: '#152238',
        muted: '#5A6779',
        line: '#C5CEDB',
        ground: '#EDF1F6',
        danger: '#A8231B',
      },
      fontFamily: {
        sans: ['"Source Sans 3 Variable"', 'system-ui', 'sans-serif'],
        serif: ['"Literata Variable"', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
}
