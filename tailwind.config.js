/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        coral: {
          black: '#0F0B0B',
          900: '#1A1413',
          800: '#241C1B',
          700: '#322827',
        },
        radioactive: {
          green: '#86BC24',
          600: '#74A41F',
          300: '#B6DD6E',
          100: '#EAF4D6',
        },
        canvas: '#FAFAF8',
        ink: '#0F0B0B',
        status: {
          ok: '#5FA23C',
          immaterial: '#C99A1E',
          material: '#C8473A',
          orphan: '#B5743C',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Space Grotesk', 'Inter', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(15,11,11,0.04), 0 6px 20px rgba(15,11,11,0.05)',
        lift: '0 8px 30px rgba(15,11,11,0.10)',
      },
      borderRadius: {
        xl2: '14px',
      },
    },
  },
  plugins: [],
};
