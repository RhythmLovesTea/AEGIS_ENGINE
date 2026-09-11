import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        // shadcn CSS variables
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },

        // Tactical Forensic Intelligence Tokens (Neutral Deep Zinc / Ballistic Slate)
        forensic: {
          canvas: "#0B0F14",
          panel: "#111720",
          menu: "#161F2C",
          border: "#1F2937",
          emerald: "#10B981",
          emeraldDark: "#059669",
          steel: "#38BDF8",
          steelMuted: "#64748B",
        },

        // Tactical Emerald & Steel Blue
        "brand-green": {
          DEFAULT: "#10B981", // Tactical Emerald
          deep: "#059669",
          pressed: "#047857",
          dark: "#064e3b",
          mid: "#059669",
          soft: "rgba(16, 185, 129, 0.15)",
        },
        "brand-teal": {
          deep: "#0B0F14", // Neutral Deep Zinc Canvas
          DEFAULT: "#111720", // Neutral Deep Zinc Panel
          mid: "#161F2C", // Floating Menu
        },

        // Canvas & Surfaces
        canvas: {
          DEFAULT: "#0B0F14",
          dark: "#0B0F14",
        },
        surface: {
          DEFAULT: "#111720",
          soft: "#161F2C",
          feature: "rgba(16, 185, 129, 0.1)",
        },
        hairline: {
          DEFAULT: "#1F2937",
          soft: "#1F2937",
          strong: "#374151",
          dark: "#1F2937",
        },

        // Category & Semantic Accents
        "accent-purple": "#8b5cf6",
        "accent-orange": "#f97316",
        "accent-pink": "#ec4899",
        "accent-blue": "#38BDF8", // Steel Blue
        "semantic-warning": {
          bg: "rgba(245, 158, 11, 0.15)",
          text: "#f59e0b",
        },

        // Neutrals & Typography Colors
        ink: "#0B0F14",
        charcoal: "#111720",
        slate: "#334155",
        steel: "#64748B",
        stone: "#94A3B8",
        "on-dark": {
          DEFAULT: "#F8FAFC",
          muted: "#94A3B8",
        },
      },
      borderRadius: {
        none: "0px",
        xs: "2px",
        sm: "2px",
        md: "4px",
        lg: "4px",
        xl: "4px",
        "2xl": "4px",
        full: "9999px", // Reserved strictly for 6px status LED dots
        pill: "4px",
      },
      fontFamily: {
        sans: ["Euclid Circular A", "Inter", "var(--font-sans)", "sans-serif"],
        mono: ["JetBrains Mono", "Source Code Pro", "var(--font-mono)", "monospace"],
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [tailwindcssAnimate],
};

export default config;
