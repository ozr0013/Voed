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
        // Cimento-style matte palette (landing)
        paper: "#e7e4dc",
        paper2: "#dedad0",
        coal: "#17150f",
        flame: "#ef5a24",
      },
      fontFamily: {
        display: ['"Archivo"', "Arial Narrow", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", '"Cascadia Code"', "Consolas", "monospace"],
      },
      boxShadow: {
        hard: "4px 4px 0 0 #17150f",
      },
    },
  },
  plugins: [],
};
