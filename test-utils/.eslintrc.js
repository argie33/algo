module.exports = {
  env: {
    node: true,
    es2022: true,
    jest: true
  },
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: 'commonjs'
  },
  extends: [
    'eslint:recommended'
  ],
  rules: {
    'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    'no-console': 'off',
    'no-process-exit': 'error',
    'prefer-const': 'error',
    'no-var': 'error'
  }
};