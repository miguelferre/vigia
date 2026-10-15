// ESLint 9, configuración plana. `npm run lint` limpio es criterio de
// cierre. Sin reglas con información de tipos: typescript-eslint todavía
// no soporta la API de TypeScript 7, y las reglas sintácticas bastan aquí.

import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist", "src/api/schema.d.ts", "../src/vigia/static"],
  },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Convención de shadcn (variantes junto al componente) y de los
      // contextos de Vigía (hook y constantes junto al proveedor).
      "react-refresh/only-export-components": [
        "warn",
        {
          allowConstantExport: true,
          allowExportNames: [
            "buttonVariants",
            "badgeVariants",
            "tabsListVariants",
            "colorEstado",
            "useTheme",
            "useThemeToggle",
            "useSession",
            "useCan",
            "ROLES",
            "ETIQUETA_ROL",
            "PERMISOS",
          ],
        },
      ],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "no-console": "error",
    },
  },
  {
    // Copias literales de registros de terceros (beUI, Rare UI, Beautiful UI),
    // documentadas en NOTICE. No se reescriben para satisfacer al linter:
    // dejarlas idénticas al original es lo que permite volver a instalarlas.
    files: ["src/components/beui/**", "src/components/rareui/**", "src/components/beautifului/**"],
    rules: {
      "no-console": "off",
      "@typescript-eslint/no-unused-vars": "off",
      "react-hooks/set-state-in-effect": "off",
    },
  },
  {
    files: ["scripts/**/*.mjs", "eslint.config.js", "vite.config.ts"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.node,
    },
    rules: {
      "no-console": "off",
    },
  },
);
