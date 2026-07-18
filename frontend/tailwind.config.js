/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b0e14",
        panel: "#131824",
        edge: "#232a3a",
        accent: "#5b8cff",
        good: "#3ecf8e",
        warn: "#f5a623",
        bad: "#ff5c5c",
      },
    },
  },
  plugins: [],
};
