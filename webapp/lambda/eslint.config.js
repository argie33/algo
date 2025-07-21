const js = require('@eslint/js');

module.exports = [
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: {
        require: 'readonly',
        module: 'readonly',
        exports: 'readonly',
        __dirname: 'readonly',
        __filename: 'readonly',
        process: 'readonly',
        console: 'readonly',
        Buffer: 'readonly',
        global: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        setImmediate: 'readonly',
        clearImmediate: 'readonly',
        // Browser/Node.js globals
        fetch: 'readonly',
        AbortController: 'readonly',
        URL: 'readonly',
        URLSearchParams: 'readonly',
        TextEncoder: 'readonly',
        TextDecoder: 'readonly',
        // Jest globals for test files
        describe: 'readonly',
        it: 'readonly',
        test: 'readonly',
        expect: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        jest: 'readonly'
      }
    },
    rules: {
      // Error prevention
      'no-unused-vars': ['warn', { 
        'argsIgnorePattern': '^_',
        'varsIgnorePattern': '^_'
      }],
      'no-undef': 'error',
      'no-redeclare': 'warn',
      'no-unreachable': 'warn',
      'no-duplicate-imports': 'warn',
      
      // Code quality  
      'prefer-const': 'off', // Many existing vars can be const
      'no-var': 'off', // Legacy code may use var
      'eqeqeq': ['warn', 'always'],
      'no-eval': 'error',
      'no-implied-eval': 'error',
      
      // Style (disabled for existing codebase)
      'semi': 'off',
      'quotes': 'off', 
      'indent': 'off',
      'comma-dangle': 'off',
      'no-trailing-spaces': 'off',
      'no-multiple-empty-lines': 'off',
      
      // Disable problematic rules for this codebase
      'no-console': 'off',
      'no-control-regex': 'off',
      'no-useless-escape': 'off',
      'no-case-declarations': 'off'
    },
    ignores: [
      'node_modules/**',
      'coverage/**',
      '.jest-cache/**',
      'test-results/**',
      '*.min.js'
    ]
  }
];