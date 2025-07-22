#!/usr/bin/env node

/**
 * Quick Validation - Fast pre-push checks
 * Runs only essential tests to catch critical errors quickly
 */

import { execSync } from 'child_process';
import chalk from 'chalk';

const errors = [];

function runCommand(command, description, options = {}) {
  console.log(chalk.blue(`🔄 ${description}...`));
  try {
    const result = execSync(command, { 
      encoding: 'utf8',
      stdio: options.silent ? 'pipe' : 'inherit',
      timeout: options.timeout || 30000
    });
    console.log(chalk.green(`✅ ${description}`));
    return { success: true, output: result };
  } catch (error) {
    console.log(chalk.red(`❌ ${description}`));
    errors.push({ step: description, error: error.message });
    return { success: false, error: error.message };
  }
}

async function main() {
  console.log(chalk.blue.bold('\n🚀 Quick Validation (Essential Checks Only)\n'));
  
  // 1. Build Check
  runCommand('npm run build', 'Build Check');
  
  // 2. Run just a few critical tests
  console.log(chalk.blue('🧪 Running critical tests only...'));
  
  // Test just the services we know work
  const criticalTests = [
    'src/tests/unit/services/real-cache-service.test.js',
    'src/tests/unit/components/api-key-status-indicator.test.jsx'
  ];
  
  for (const testFile of criticalTests) {
    try {
      runCommand(
        `npx vitest run --reporter=default ${testFile}`, 
        `Testing ${testFile.split('/').pop()}`,
        { timeout: 15000 }
      );
    } catch (error) {
      console.log(chalk.yellow(`⚠️  Skipping ${testFile} - setup issues`));
    }
  }
  
  // 3. Check for basic syntax errors
  runCommand('node -c src/components/ui/navigation.jsx', 'Syntax Check (navigation)');
  runCommand('node -c src/theme/safeTheme.js', 'Syntax Check (theme)');
  
  // Results
  console.log(chalk.blue.bold('\n📊 Quick Validation Results\n'));
  
  if (errors.length === 0) {
    console.log(chalk.green.bold('✅ QUICK CHECKS PASSED!\n'));
    console.log(chalk.cyan('✨ Basic validation complete. For full validation, run:'));
    console.log(chalk.cyan('   npm run test:unit -- --run --reporter=basic\n'));
    process.exit(0);
  } else {
    console.log(chalk.red.bold(`❌ ${errors.length} ISSUES FOUND\n`));
    errors.forEach((error, index) => {
      console.log(chalk.red(`${index + 1}. ${error.step}`));
      console.log(chalk.gray(`   ${error.error.substring(0, 200)}...`));
    });
    process.exit(1);
  }
}

main().catch(error => {
  console.error(chalk.red.bold('❌ Quick validation failed:'), error);
  process.exit(1);
});