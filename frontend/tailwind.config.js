/** @type {import('tailwindcss').Config} */

/* Colours resolve through CSS variables defined in index.css, so light and
   dark are one definition each rather than a `dark:` prefix on every class.
   The semantic names (ground / surface / ink / accent / band-N) are what the
   views use; the brand names below are for new work that genuinely needs a
   fixed brand colour, such as the logo mark. */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
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
        lineStrong: "var(--line-strong)",
        accent: "var(--accent)",
        accentSoft: "var(--accent-soft)",
        onAccent: "var(--on-accent)",
        energy: "var(--energy)",
        energyInk: "var(--energy-ink)",
        band1: "var(--band-1)",
        band2: "var(--band-2)",
        band3: "var(--band-3)",
        band4: "var(--band-4)",

        // Fixed brand colours, from the EvalNova brand kit. Used where a
        // colour must not follow the theme - the logo, the one gradient.
        navy: { 950: "#00081E", 900: "#000E31", 850: "#001241", 800: "#00164F" },
        nova: { 600: "#0B59CF", 500: "#0E6CFD", 400: "#5698FD", 100: "#E0ECFD" },
        scan: { 700: "#006E97", 500: "#00B2F3", 300: "#83D5F3" },
        ice: "#B9DCFE",
      },
      fontFamily: {
        // One family, per the brand kit. `display` and `body` both resolve to
        // it so the existing class names keep working.
        display: ['"Plus Jakarta Sans"', "system-ui", "-apple-system", "sans-serif"],
        body: ['"Plus Jakarta Sans"', "system-ui", "-apple-system", "sans-serif"],
        // Kept as a second face on purpose: transcribed text, bounding boxes
        // and model identifiers are data, and proportional digits make them
        // harder to compare line against line.
        mono: ['"JetBrains Mono"', "Consolas", "monospace"],
      },
      letterSpacing: {
        tightest: "-.045em",
        label: ".18em",
      },
      borderRadius: {
        DEFAULT: "10px",
        md: "10px",
        lg: "16px",
        xl: "24px",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        accent: "var(--shadow-accent)",
      },
      backgroundImage: {
        "nova-grad": "linear-gradient(105deg,#00B2F3,#0E6CFD 62%)",
        "nova-depth": "linear-gradient(160deg,#000E31,#00164F 45%,#002A96)",
      },
      transitionTimingFunction: {
        nova: "cubic-bezier(.4,0,.2,1)",
        beam: "cubic-bezier(.55,0,.45,1)",
      },
      animation: {
        "ev-glow": "ev-glow 9s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
