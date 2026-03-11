/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    extend: {
      colors: {
        shell: "#0f1720",
        panel: "#f7f4ec",
        ink: "#182230",
        accent: "#f97316",
        tide: "#0f766e",
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"],
        body: ["Manrope", "sans-serif"],
      },
      boxShadow: {
        card: "0 24px 48px rgba(15, 23, 32, 0.12)",
      },
    },
  },
  plugins: [],
};
