module.exports = {
  env: {
    browser: false,
    es6: true,
    node: true,
    jest: true,
    mocha: true
  },
  extends: ['eslint:recommended'],
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: 'module'
  },
  globals: {
    describe: 'readonly',
    it: 'readonly',
    expect: 'readonly',
    test: 'readonly',
    beforeEach: 'readonly',
    afterEach: 'readonly',
    before: 'readonly',
    after: 'readonly'
  },
  rules: {
    'no-console': 'warn',
    'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    'require-await': 'warn',
    'no-undef': 'error',
    'no-debugger': 'error',
    'no-unreachable': 'error',
    'no-duplicate-imports': 'error',
    'prefer-const': 'error',
    'no-var': 'error'
  }
};