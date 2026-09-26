/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#0b0e13", 900: "#10141b", 850: "#141922", 800: "#19202b", 700: "#232c3a", 600: "#2f3a4b", 500: "#4a5668", 400: "#6f7b8f", 300: "#9aa5b8", 200: "#c4ccd8", 100: "#e3e8ef" },
        accent: { DEFAULT: "#4ea1ff", dim: "#2d5f99" },
        signal: "#e0a341",
        hypo: "#b48cff",
        verified: "#43c59e",
        danger: "#e5534b",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: { "2xs": ["10px", "13px"], xs: ["11px", "15px"], sm: ["12px", "16px"] },
    },
  },
  plugins: [],
};
