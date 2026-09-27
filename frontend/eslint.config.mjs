import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";
import jsxA11y from "eslint-plugin-jsx-a11y";
import tseslint from "typescript-eslint";

// Spec §14.2: next/core-web-vitals + typescript-eslint strict-type-checked + jsx-a11y,
// with Prettier owning formatting.
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["**/*.{ts,tsx,mts}"],
    extends: [tseslint.configs.strictTypeChecked, tseslint.configs.stylisticTypeChecked],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  {
    // eslint-config-next already registers the jsx-a11y plugin; enable its full
    // recommended rule set without redefining the plugin.
    files: ["**/*.{js,jsx,mjs,ts,tsx,mts}"],
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
      // Server Actions and the 'use cache' directive are banned (spec §12.7, A-24): every
      // mutation goes through the FastAPI API with cookie auth + CSRF header, and
      // per-user pages are never cached. CI also greps for both directives.
      "no-restricted-syntax": [
        "error",
        {
          selector: "ExpressionStatement[directive='use server']",
          message: "Server Actions are not allowed; call the FastAPI API via src/lib/api instead.",
        },
        {
          selector: "ExpressionStatement[directive='use cache']",
          message: "'use cache' is not allowed: pages are per-user and dynamically rendered.",
        },
      ],
    },
  },
  prettier,
  globalIgnores([".next/**", "out/**", "build/**", "coverage/**", "next-env.d.ts"]),
]);

export default eslintConfig;
