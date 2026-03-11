import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Core dark racing palette
        race: {
          bg: "#0a0a0a",
          surface: "#111111",
          card: "#1a1a1a",
          border: "#2a2a2a",
          muted: "#666666",
          text: "#e5e5e5",
        },
        // F1 team colors
        team: {
          redbull: "#3671C6",
          ferrari: "#E80020",
          mclaren: "#FF8000",
          mercedes: "#27F4D2",
          astonmartin: "#229971",
          alpine: "#FF87BC",
          williams: "#64C4FF",
          haas: "#B6BABD",
          rb: "#6692FF",
          sauber: "#52E252",
        },
        // Data visualization
        telemetry: {
          speed: "#00D4FF",
          throttle: "#00FF87",
          brake: "#FF3B3B",
          steering: "#FFD700",
          gear: "#B388FF",
          drs: "#FF6B00",
          delta: {
            positive: "#FF3B3B",
            negative: "#00FF87",
          },
        },
        // Tire compound colors
        tire: {
          soft: "#FF3B3B",
          medium: "#FFD700",
          hard: "#FFFFFF",
          intermediate: "#00FF87",
          wet: "#00A3FF",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      fontSize: {
        "data-xs": ["0.65rem", { lineHeight: "1", letterSpacing: "0.05em" }],
        "data-sm": ["0.75rem", { lineHeight: "1.2", letterSpacing: "0.02em" }],
        "data-md": ["0.875rem", { lineHeight: "1.2", letterSpacing: "0.01em" }],
        "data-lg": ["1.125rem", { lineHeight: "1.2" }],
        "data-xl": ["1.5rem", { lineHeight: "1" }],
        "data-2xl": ["2rem", { lineHeight: "1" }],
      },
      animation: {
        "pulse-fast": "pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-in-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      boxShadow: {
        glow: "0 0 20px rgba(0, 212, 255, 0.15)",
        "glow-red": "0 0 20px rgba(255, 59, 59, 0.15)",
        "glow-green": "0 0 20px rgba(0, 255, 135, 0.15)",
      },
    },
  },
  plugins: [],
};

export default config;
