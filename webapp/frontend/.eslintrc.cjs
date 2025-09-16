module.exports = {
  root: true,
  env: {
    browser: true,
    es2020: true,
    node: true,
    jest: true,
  },
  extends: [
    "eslint:recommended",
    "plugin:react/recommended",
    "plugin:react-hooks/recommended",
  ],
  ignorePatterns: ["dist", ".eslintrc.cjs"],
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: {
      jsx: true,
    },
  },
  settings: {
    react: {
      version: "detect",
    },
  },
  plugins: ["react-refresh", "react", "unused-imports"],
  rules: {
    "react-refresh/only-export-components": [
      "warn",
      { allowConstantExport: true },
    ],
    "react/prop-types": "off", // Disable prop-types validation
    "no-unused-vars": "off",
    "unused-imports/no-unused-imports": "error",
    "unused-imports/no-unused-vars": [
      "warn",
      {
        vars: "all",
        varsIgnorePattern: "^_",
        args: "after-used",
        argsIgnorePattern: "^_",
      },
    ],
    "react/react-in-jsx-scope": "off", // Not needed for React 17+
    "react/display-name": "off", // Allow anonymous components
    "react-hooks/exhaustive-deps": "warn",

    // Additional React compatibility and best practice rules
    "react/jsx-uses-react": "off", // Not needed for React 17+
    "react/jsx-uses-vars": "error", // Prevent variables used in JSX being marked as unused
    "react/no-deprecated": "error", // Prevent usage of deprecated methods
    "react/no-unsafe": "warn", // Warn about unsafe lifecycle methods
    "react/jsx-no-target-blank": "error", // Security: prevent target="_blank" without rel="noopener"
    "react/jsx-key": "error", // Require key prop in lists
    "react/no-array-index-key": "off", // Temporarily disabled due to widespread usage
    "react/self-closing-comp": "error", // Enforce self-closing for components without children
  },
  overrides: [
    {
      files: [
        "**/*.test.js",
        "**/*.test.jsx",
        "**/*.spec.js",
        "**/*.spec.jsx",
        "**/tests/**/*.js",
        "**/tests/**/*.jsx",
      ],
      env: {
        jest: true,
      },
      globals: {
        describe: "readonly",
        it: "readonly",
        test: "readonly",
        expect: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
        beforeAll: "readonly",
        afterAll: "readonly",
        jest: "readonly",
        vi: "readonly",
      },
    },
  ],
};
