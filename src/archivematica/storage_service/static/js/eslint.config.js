const js = require("@eslint/js");
const globals = require("globals");
const eslintPluginPrettierRecommended = require("eslint-plugin-prettier/recommended");

/** @type {import("eslint").Linter.FlatConfig[]} */
module.exports = [
  {
    ...js.configs.recommended,
    languageOptions: {
      ...js.configs.recommended.languageOptions,
      sourceType: "script",
      globals: {
        ...globals.browser,
        ...globals.jquery,
        gettext: "readonly",
      },
    },
  },
  eslintPluginPrettierRecommended,
];
