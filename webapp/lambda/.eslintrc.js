module.exports = {
  root: true,
  env: {
    browser: false,
    node: true,
    es2020: true,
    jest: true,
  },
  extends: ["eslint:recommended"],
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
  },
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
  },
};
