import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: ["node_modules/**", "frontend/locales/**"],
  },
  js.configs.recommended,
  {
    files: ["frontend/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        Chart: "readonly",
      },
    },
    rules: {
      "no-unused-vars": ["error", { args: "none" }],
      "prefer-const": "warn",
      "no-var": "error",
    },
  },
];
