/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        indigo: {
          950: '#1e1b4b',
        },
        teal: {
          400: '#2dd4bf',
          500: '#14b8a6',
        }
      }
    },
  },
  plugins: [],
}
