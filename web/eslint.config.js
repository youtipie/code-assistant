import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.strictTypeChecked],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { project: ["./tsconfig.json"], tsconfigRootDir: import.meta.dirname },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-misused-promises": ["error", { checksVoidReturn: false }],

      // Two strictTypeChecked rules this codebase has never followed, relaxed
      // rather than worked around at 19 call sites.
      // Numbers in template literals are idiomatic here (`${path}:${line}`).
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
      // Fights the standard React/zustand handler shorthand
      // (`onChange={(e) => setValue(e.target.value)}`).
      "@typescript-eslint/no-confusing-void-expression": "off",
    },
  },
);
