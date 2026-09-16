/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ground: "var(--ground)",
        surface: "var(--surface)",
        surface2: "var(--surface-2)",
        ink: "var(--ink)",
        ink2: "var(--ink-2)",
        ink3: "var(--ink-3)",
        line: "var(--line)",
        accent: "var(--accent)",
        accentSoft: "var(--accent-soft)",
        band1: "var(--band-1)",
        band2: "var(--band-2)",
        band3: "var(--band-3)",
        band4: "var(--band-4)",
      },
      fontFamily: {
        display: ["Archivo", "Helvetica Neue", "Arial", "sans-serif"],
        body: ["Source Serif 4", "Georgia", "serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
