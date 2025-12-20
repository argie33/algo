module.exports = [
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      globals: {
        console: "readonly",
        process: "readonly",
        Buffer: "readonly",
        __dirname: "readonly",
        __filename: "readonly",
        exports: "writable",
        global: "readonly",
        module: "writable",
        require: "readonly"
      }
    },
    rules: {
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "no-console": "off",
      "no-process-exit": "error",
      "prefer-const": "error",
      "no-var": "error"
    }
  }
];