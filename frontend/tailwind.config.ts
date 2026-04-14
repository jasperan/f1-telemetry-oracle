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
        // Core dark racing palette (warm-tinted charcoals)
        race: {
          bg: "#0c0c0e",
          surface: "#131316",
          card: "#1a1a1f",
          border: "#26262e",
          muted: "#6b6b78",
          text: "#e8e8ed",
          "text-secondary": "#a0a0ae",
        },
        // Unified accent system (desaturated for premium feel)
        accent: {
          primary: "#4cb8d4",    // teal-cyan, sat ~65%
          positive: "#45d48a",   // green, sat ~60%
          negative: "#e05555",   // red, sat ~65%
          warning: "#d4a845",    // amber, sat ~60%
          purple: "#9b7ee8",     // violet, sat ~55%
          orange: "#d47a3c",     // orange, sat ~60%
        },
        // F1 team colors (kept authentic, slightly tamed)
        team: {
          redbull: "#3671C6",
          ferrari: "#D42020",
          mclaren: "#E87400",
          mercedes: "#27D4B8",
          astonmartin: "#229971",
          alpine: "#E87BAC",
          williams: "#5EAEE8",
          haas: "#A8ACB0",
          rb: "#5E86E8",
          sauber: "#4AD44A",
        },
        // Data visualization (desaturated ~20% from originals)
        telemetry: {
          speed: "#4cb8d4",
          throttle: "#45d48a",
          brake: "#e05555",
          steering: "#d4a845",
          gear: "#9b7ee8",
          drs: "#d47a3c",
          delta: {
            positive: "#e05555",
            negative: "#45d48a",
          },
        },
        // Tire compound colors (slightly desaturated)
        tire: {
          soft: "#e05555",
          medium: "#d4a845",
          hard: "#e8e8ed",
          intermediate: "#45d48a",
          wet: "#4ca8e0",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "monospace"],
        sans: ["Outfit", "system-ui", "sans-serif"],
      },
      fontSize: {
        "data-xs": ["0.65rem", { lineHeight: "1.1", letterSpacing: "0.06em" }],
        "data-sm": ["0.75rem", { lineHeight: "1.3", letterSpacing: "0.015em" }],
        "data-md": ["0.875rem", { lineHeight: "1.3", letterSpacing: "0" }],
        "data-lg": ["1.125rem", { lineHeight: "1.2", letterSpacing: "-0.01em" }],
        "data-xl": ["1.5rem", { lineHeight: "1", letterSpacing: "-0.02em" }],
        "data-2xl": ["2rem", { lineHeight: "1", letterSpacing: "-0.03em" }],
        "data-3xl": ["2.5rem", { lineHeight: "0.9", letterSpacing: "-0.04em" }],
      },
      animation: {
        "pulse-fast": "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "fade-in-up": "fadeInUp 0.5s cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in": "slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in": "scaleIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideIn: {
          "0%": { opacity: "0", transform: "translateX(-4px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
      boxShadow: {
        glow: "0 0 24px rgba(76, 184, 212, 0.12), 0 0 8px rgba(76, 184, 212, 0.06)",
        "glow-red": "0 0 24px rgba(224, 85, 85, 0.12), 0 0 8px rgba(224, 85, 85, 0.06)",
        "glow-green": "0 0 24px rgba(69, 212, 138, 0.12), 0 0 8px rgba(69, 212, 138, 0.06)",
        "panel": "0 1px 3px rgba(0, 0, 0, 0.3), 0 4px 12px rgba(0, 0, 0, 0.15)",
        "panel-hover": "0 2px 8px rgba(0, 0, 0, 0.35), 0 8px 24px rgba(0, 0, 0, 0.2)",
        "inner-highlight": "inset 0 1px 0 0 rgba(255, 255, 255, 0.04)",
      },
      borderRadius: {
        panel: "0.75rem",
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
