#!/usr/bin/env node

/**
 * Simple Pre-Push Validation
 * Just the essentials: build + one working test
 */

import { execSync } from 'child_process';
import chalk from 'chalk';

console.log(chalk.blue.bold('🚀 Simple Pre-Push Validation\n'));

try {
  // 1. Build Check
  console.log(chalk.blue('🏗️  Checking build...'));
  execSync('npm run build', { stdio: 'inherit' });
  console.log(chalk.green('✅ Build successful\n'));
  
  // 2. Run one simple test to verify test setup
  console.log(chalk.blue('🧪 Running quick test...'));
  const result = execSync('npx vitest run --reporter=basic src/tests/unit/simple-unit-test.test.js', { 
    encoding: 'utf8',
    stdio: 'pipe' 
  });
  console.log(chalk.green('✅ Tests working\n'));
  
  console.log(chalk.green.bold('🎉 VALIDATION PASSED!'));
  console.log(chalk.cyan('\n✨ Your changes are ready to push!'));
  console.log(chalk.gray('   git add . && git commit -m "Your message" && git push\n'));
  
} catch (error) {
  console.log(chalk.red.bold('\n❌ VALIDATION FAILED'));
  console.log(chalk.red('Fix these issues before pushing:\n'));
  console.log(chalk.gray(error.message));
  console.log();
  process.exit(1);
}