import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b0e14",
        panel: "#141923",
        panel2: "#1c2230",
        edge: "#2a3242",
        muted: "#8a94a6",
        accent: "#f5b301", // beer amber
        good: "#34d399",
        bad: "#f87171",
        warn: "#fbbf24",
      },
      fontFamily: {
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
