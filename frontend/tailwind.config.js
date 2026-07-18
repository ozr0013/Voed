/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#000000",
        panel: "#0b0b0c",
        edge: "#1f1f22",
        accent: "#C8102E", // Spain Red
        good: "#3ecf8e",
        warn: "#C8102E",   // Replace yellow with red
        bad: "#ff5c5c",
        // Cimento-style palette mapped to black/red theme
        paper: "#000000",
        paper2: "#0b0b0c",
        coal: "#ffffff",   // White instead of Spain Gold
        flame: "#C8102E",  // Spain Red
      },
      fontFamily: {
        display: ['"Archivo"', "Arial Narrow", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", '"Cascadia Code"', "Consolas", "monospace"],
      },
      boxShadow: {
        hard: "4px 4px 0 0 #03091a",
      },
    },
  },
  plugins: [],
};
