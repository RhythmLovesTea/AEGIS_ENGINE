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

        // DESIGN.md Brand Colors
        "brand-green": {
          DEFAULT: "#00ed64",
          deep: "#00b545",
          pressed: "#008c34",
          dark: "#00684a",
          mid: "#00a35c",
          soft: "#c3f0d2",
        },
        "brand-teal": {
          deep: "#001e2b",
          DEFAULT: "#003d4f",
          mid: "#00684a",
        },

        // DESIGN.md Canvas & Surfaces
        canvas: {
          DEFAULT: "#ffffff",
          dark: "#001e2b",
        },
        surface: {
          DEFAULT: "#f9fbfa",
          soft: "#f4f7f6",
          feature: "#e3fcef",
        },
        hairline: {
          DEFAULT: "#e1e5e8",
          soft: "#eceff1",
          strong: "#c1ccd6",
          dark: "#1c2d38",
        },

        // DESIGN.md Category & Semantic Accents
        "accent-purple": "#7b3ff2",
        "accent-orange": "#fa6e39",
        "accent-pink": "#f06bb8",
        "accent-blue": "#3d4f9f",
        "semantic-warning": {
          bg: "#fff8e0",
          text: "#946f3f",
        },

        // DESIGN.md Neutrals & Typography Colors
        ink: "#001e2b",
        charcoal: "#1c2d38",
        slate: "#3d4f5b",
        steel: "#5c6c7a",
        stone: "#7c8c9a",
        "on-dark": {
          DEFAULT: "#ffffff",
          muted: "#a8b3bc",
        },
      },
      borderRadius: {
        xs: "4px",
        sm: "6px",
        md: "8px",
        lg: "12px",
        xl: "16px",
        "2xl": "24px",
        full: "9999px",
        pill: "9999px",
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
