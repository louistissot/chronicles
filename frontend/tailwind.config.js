/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx,js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
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
        gold: {
          DEFAULT: "#D4AF37",
          light: "#F0CC50",
          dark: "#A88A1C",
          muted: "#8B7228",
        },
        arcane: {
          DEFAULT: "#7C3AED",
          light: "#9D5CF0",
          dark: "#5B21B6",
        },
        parchment: "rgb(var(--parchment) / <alpha-value>)",
        void:      "rgb(var(--void)      / <alpha-value>)",
        abyss:     "rgb(var(--abyss)     / <alpha-value>)",
        shadow:    "rgb(var(--shadow)    / <alpha-value>)",
      },
      fontFamily: {
        display: ["'Cinzel Decorative'", "serif"],
        heading: ["'Cinzel'", "serif"],
        body: ["'Inter'", "sans-serif"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
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
        "glow-pulse": {
          "0%, 100%": { textShadow: "0 0 8px rgba(212, 175, 55, 0.6), 0 0 20px rgba(212, 175, 55, 0.3)" },
          "50%": { textShadow: "0 0 16px rgba(212, 175, 55, 0.9), 0 0 40px rgba(212, 175, 55, 0.5)" },
        },
        "shimmer": {
          "0%": { backgroundPosition: "-200% center" },
          "100%": { backgroundPosition: "200% center" },
        },
        "float": {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-4px)" },
        },
      },
      animation: {
        "glow-pulse": "glow-pulse 3s ease-in-out infinite",
        "shimmer": "shimmer 3s linear infinite",
        "float": "float 4s ease-in-out infinite",
      },
      backgroundImage: {
        "gold-shimmer": "linear-gradient(90deg, transparent 0%, rgba(212,175,55,0.15) 50%, transparent 100%)",
        "void-gradient": "radial-gradient(ellipse at top, #12172A 0%, #080B14 70%)",
        "arcane-glow": "radial-gradient(ellipse at center, rgba(124, 58, 237, 0.1) 0%, transparent 70%)",
      },
    },
  },
  plugins: [],
}
