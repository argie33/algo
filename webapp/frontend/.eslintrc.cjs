module.exports = {
  root: true,
  env: { 
    browser: true, 
    es2020: true,
    node: true
  },
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: {
      jsx: true,
    },
  },
  settings: {
    react: {
      version: 'detect',
    },
  },
  plugins: ['react-refresh', 'react'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
    'react/prop-types': 'off', // Disable prop-types validation
    'no-unused-vars': ['error', { 
      "varsIgnorePattern": "^_",
      "argsIgnorePattern": "^_",
      "ignoreRestSiblings": true
    }],
    'react/react-in-jsx-scope': 'off', // Not needed for React 17+
    'react/display-name': 'off', // Allow anonymous components
    'react-hooks/exhaustive-deps': 'warn',
  },
}