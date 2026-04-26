/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        poppins: ["Poppins", "sans-serif"],
      },
      colors: {
        brand: {
          50: "#FFFCE6",
          100: "#FFF690",
          200: "#FBEC5D",
          300: "#FFDE39",
          400: "#FFDE39",
          500: "#FBEC5D",
          600: "#E6C800",
        },
        dark: {
          100: "#444342",
          200: "#2A2929",
          300: "#1F1F1F",
        },
        sidebar: {
          DEFAULT: "#1F1F1F",
          hover: "#2A2929",
          active: "#444342",
        },
      },
      keyframes: {
        fadeIn: {
          "0%":   { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideUp: {
          "0%":   { opacity: "0", transform: "translateY(24px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fadeScale: {
          "0%":   { opacity: "0", transform: "scale(0.97) translateY(8px)" },
          "100%": { opacity: "1", transform: "scale(1) translateY(0)" },
        },
      },
      animation: {
        fadeIn:    "fadeIn 0.45s cubic-bezier(0.16,1,0.3,1) both",
        slideUp:   "slideUp 0.5s cubic-bezier(0.16,1,0.3,1) both",
        fadeScale: "fadeScale 0.4s cubic-bezier(0.16,1,0.3,1) both",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
}

