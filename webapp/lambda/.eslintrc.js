module.exports = {
  root: true,
  env: {
    browser: false,
    node: true,
    es2020: true,
    jest: true,
  },
  extends: [
    "eslint:recommended",
    "plugin:node/recommended",
    "plugin:import/recommended",
  ],
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
  },
  plugins: ["node", "import"],
  rules: {
    "no-unused-vars": [
      "warn",
      {
        vars: "all",
        varsIgnorePattern: "^_",
        args: "after-used",
        argsIgnorePattern: "^_",
      },
    ],
    "no-console": "off", // Allow console.log in backend
    "no-undef": "error",

    // Security rules (manual)
    "no-eval": "error",
    "no-implied-eval": "error",
    "no-new-func": "error",

    // Node.js best practices
    "node/no-deprecated-api": "error",
    "node/no-extraneous-import": "error",
    "node/no-extraneous-require": "error",
    "node/no-missing-import": "off", // Sometimes false positives with AWS SDK
    "node/no-missing-require": "error",
    "node/no-unpublished-import": "off", // Allow devDependencies in tests
    "node/no-unsupported-features/es-syntax": "off", // Allow modern ES syntax

    // Import/Export rules
    "import/no-unresolved": "off", // AWS SDK modules sometimes unresolved
    "import/order": [
      "warn",
      {
        groups: [
          "builtin",
          "external",
          "internal",
          "parent",
          "sibling",
          "index",
        ],
        "newlines-between": "always",
      },
    ],
    "import/no-duplicates": "error",
    "import/no-unused-modules": "warn",

    strict: ["error", "global"],
  },
  overrides: [
    {
      files: ["tests/**/*.js", "**/*.test.js", "**/*.spec.js"],
      rules: {
        "node/no-unpublished-import": "off",
        "node/no-unpublished-require": "off",
        "import/order": "off", // Disable import order for test files
        // Test-specific rule adjustments
      },
    },
    {
      files: [
        "debug_*.js",
        "test_*.js",
        "fix_*.js",
        "*_test.js",
        "run_*.js",
        "scripts/**/*.js",
        "tests/**/*.js",
        "setup_*.js",
        "apply_*.js",
        "add_*.js",
      ],
      rules: {
        "node/no-unpublished-import": "off",
        "node/no-unpublished-require": "off",
        "no-process-exit": "off", // Allow process.exit in debug/test scripts
        "no-useless-catch": "off", // Allow catch blocks in test scripts
      },
    },
  ],
};
