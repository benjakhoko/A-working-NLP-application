/** Tailwind configuration (compiled with the standalone CLI, no Node.js required). */
module.exports = {
  content: [
    "./frontend/templates/**/*.html",
    "./frontend/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: "#0B1220",
          900: "#0B1220",
          800: "#111C31",
          700: "#17233A",
          600: "#22324F",
        },
        accent: {
          DEFAULT: "#2563EB",
          dark: "#1D4ED8",
          soft: "#EFF6FF",
        },
        ink: { DEFAULT: "#111827", muted: "#64748B" },
        line: "#E5E7EB",
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
      borderRadius: { DEFAULT: "7px" },
    },
  },
  plugins: [],
};
