/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",],
  theme: {
    screens:	{
      xs: "480px",
      ss: "620px",
      sm: "768px",
      md: "1060px",
      lg: "1200px",
      xl: "1700px",
        },
    extend: {
          keyframes: {
            customSpin: {
              '0%': { transform: 'rotate(0deg)' },
              '100%': { transform: 'rotate(360deg)' },
            },
          },
          animation: {
            'custom-spin': 'customSpin 1s linear infinite',
          },
        },
  },
  plugins: [],
}