// ESLint for the front end (ui/): Vue's and typescript-eslint's recommended rules; formatting is Prettier's.
import pluginVue from "eslint-plugin-vue";
import { defineConfigWithVueTs, vueTsConfigs } from "@vue/eslint-config-typescript";
import skipFormatting from "@vue/eslint-config-prettier/skip-formatting";

export default defineConfigWithVueTs(
  { ignores: ["src/wikicross/web/**", "extension/dist/**"] },
  pluginVue.configs["flat/recommended"],
  vueTsConfigs.recommended,
  skipFormatting,
  {
    rules: {
      // `_name`: a parameter kept for its type, e.g. an emit validator's, which only types the event.
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
);
