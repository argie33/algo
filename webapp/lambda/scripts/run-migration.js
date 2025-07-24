#!/usr/bin/env node
/**
 * API Key Migration Runner
 * Migrates existing API keys to the unified system
 */

const path = require('path');
const readline = require('readline');

// Add the parent directory to require path
const parentDir = path.resolve(__dirname, '..');
require('module').globalPaths.push(parentDir);

const migrationService = require('../utils/apiKeyMigrationService');

const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m'
};

function log(message, color = 'reset') {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

function createInterface() {
  return readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });
}

function askQuestion(rl, question) {
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      resolve(answer.trim().toLowerCase());
    });
  });
}

async function runInteractiveMigration() {
  const rl = createInterface();
  
  try {
    log('🔄 API Key Migration Tool', 'cyan');
    log('=' * 50, 'cyan');
    
    // Check current status first
    log('\n📊 Checking current migration status...', 'blue');
    const stats = await migrationService.getStatus();
    
    if (stats.total > 0) {
      log(`\nCurrent Status:`, 'yellow');
      log(`Total keys: ${stats.total}`, 'cyan');
      log(`Migrated: ${stats.migrated}`, 'green');
      log(`Failed: ${stats.failed}`, 'red');
      log(`Pending: ${stats.pending}`, 'yellow');
    }
    
    log('\nMigration Options:', 'blue');
    log('1. Dry run (test migration without changes)', 'cyan');
    log('2. Full migration (migrate all keys)', 'cyan');
    log('3. Batch migration (migrate in small batches)', 'cyan');
    log('4. Check status only', 'cyan');
    log('5. Rollback migration', 'cyan');
    log('6. Exit', 'cyan');
    
    const choice = await askQuestion(rl, '\nSelect option (1-6): ');
    
    switch (choice) {
      case '1':
        await runDryRun();
        break;
      case '2':
        await runFullMigration(rl);
        break;
      case '3':
        await runBatchMigration(rl);
        break;
      case '4':
        await checkStatus();
        break;
      case '5':
        await runRollback(rl);
        break;
      case '6':
        log('👋 Goodbye!', 'green');
        break;
      default:
        log('❌ Invalid option selected', 'red');
    }
    
  } catch (error) {
    log(`💥 Migration failed: ${error.message}`, 'red');
  } finally {
    rl.close();
  }
}

async function runDryRun() {
  log('\n🧪 Running dry run migration...', 'blue');
  
  try {
    const result = await migrationService.runMigration({ 
      dryRun: true, 
      batchSize: 10 
    });
    
    log('\n📊 Dry Run Results:', 'green');
    log(`Total keys discovered: ${result.total}`, 'cyan');
    log(`Would migrate: ${result.migrated}`, 'green');
    log(`Would skip: ${result.skipped}`, 'yellow');
    log(`Would fail: ${result.failed}`, 'red');
    
    if (result.errors.length > 0) {
      log('\n⚠️ Potential Issues:', 'yellow');
      result.errors.forEach((error, index) => {
        log(`${index + 1}. ${error.type}: ${error.error}`, 'yellow');
      });
    }
    
  } catch (error) {
    log(`❌ Dry run failed: ${error.message}`, 'red');
  }
}

async function runFullMigration(rl) {
  log('\n⚠️ Full migration will migrate ALL API keys to the unified system.', 'yellow');
  const confirm = await askQuestion(rl, 'Are you sure? (yes/no): ');
  
  if (confirm !== 'yes') {
    log('Migration cancelled.', 'yellow');
    return;
  }
  
  log('\n🚀 Running full migration...', 'blue');
  
  try {
    const result = await migrationService.runMigration({ 
      dryRun: false, 
      batchSize: 5,
      delayBetweenBatches: 2000 // 2 second delay
    });
    
    log('\n📊 Migration Results:', 'green');
    log(`Total keys: ${result.total}`, 'cyan');
    log(`Successfully migrated: ${result.migrated}`, 'green');
    log(`Skipped: ${result.skipped}`, 'yellow');
    log(`Failed: ${result.failed}`, 'red');
    
    if (result.errors.length > 0) {
      log('\n❌ Errors encountered:', 'red');
      result.errors.forEach((error, index) => {
        log(`${index + 1}. ${error.type}: ${error.error}`, 'red');
      });
    }
    
  } catch (error) {
    log(`❌ Migration failed: ${error.message}`, 'red');
  }
}

async function runBatchMigration(rl) {
  const batchSizeAnswer = await askQuestion(rl, 'Enter batch size (default 5): ');
  const batchSize = parseInt(batchSizeAnswer) || 5;
  
  const delayAnswer = await askQuestion(rl, 'Enter delay between batches in seconds (default 2): ');
  const delay = (parseInt(delayAnswer) || 2) * 1000;
  
  log(`\n🔄 Running batch migration (batch size: ${batchSize}, delay: ${delay/1000}s)...`, 'blue');
  
  try {
    const result = await migrationService.runMigration({ 
      dryRun: false, 
      batchSize,
      delayBetweenBatches: delay
    });
    
    log('\n📊 Batch Migration Results:', 'green');
    log(`Total keys: ${result.total}`, 'cyan');
    log(`Successfully migrated: ${result.migrated}`, 'green');
    log(`Skipped: ${result.skipped}`, 'yellow');
    log(`Failed: ${result.failed}`, 'red');
    
  } catch (error) {
    log(`❌ Batch migration failed: ${error.message}`, 'red');
  }
}

async function checkStatus() {
  log('\n📊 Checking migration status...', 'blue');
  
  try {
    // Get migration stats from database service
    const unifiedService = require('../utils/unifiedApiKeyService');
    const status = await unifiedService.getMigrationStatus();
    
    log('\n📈 Migration Status:', 'cyan');
    log(`Total API keys: ${status.total}`, 'cyan');
    log(`Migrated to Parameter Store: ${status.migrated}`, 'green');
    log(`Pending migration: ${status.pending}`, 'yellow');
    log(`Failed migrations: ${status.failed}`, 'red');
    
    if (status.total > 0) {
      const completionRate = ((status.migrated / status.total) * 100).toFixed(2);
      log(`Completion rate: ${completionRate}%`, completionRate > 90 ? 'green' : 'yellow');
    }
    
    // Also check service health
    log('\n🏥 Service Health:', 'blue');
    const healthCheck = await unifiedService.healthCheck();
    
    if (healthCheck.healthy) {
      log('✅ Unified API Key Service is healthy', 'green');
      log(`Cache utilization: ${healthCheck.cache.utilizationPercent}%`, 'cyan');
      log(`Cache hit rate: ${healthCheck.cache.hitRate}`, 'cyan');
    } else {
      log('❌ Service health issues detected', 'red');
      log(`Error: ${healthCheck.error}`, 'red');
    }
    
  } catch (error) {
    log(`❌ Status check failed: ${error.message}`, 'red');
  }
}

async function runRollback(rl) {
  log('\n⚠️ Rollback will remove API keys from the unified system.', 'yellow');
  log('This is primarily for testing purposes.', 'yellow');
  
  const confirm = await askQuestion(rl, 'Are you sure you want to rollback? (yes/no): ');
  
  if (confirm !== 'yes') {
    log('Rollback cancelled.', 'yellow');
    return;
  }
  
  log('\n🔄 Running rollback...', 'blue');
  
  try {
    const result = await migrationService.rollbackMigration();
    
    log('\n📊 Rollback Results:', 'cyan');
    log(`Keys processed: ${result.rollbackCount}`, 'cyan');
    
    if (result.errors.length > 0) {
      log(`Errors: ${result.errors.length}`, 'red');
      result.errors.forEach((error, index) => {
        log(`${index + 1}. User ${error.userId}: ${error.error}`, 'red');
      });
    } else {
      log('✅ Rollback completed successfully', 'green');
    }
    
  } catch (error) {
    log(`❌ Rollback failed: ${error.message}`, 'red');
  }
}

// Command line arguments handling
async function handleCommandLine() {
  const args = process.argv.slice(2);
  
  if (args.length === 0) {
    return runInteractiveMigration();
  }
  
  const command = args[0].toLowerCase();
  
  switch (command) {
    case 'dry-run':
    case 'dryrun':
      await runDryRun();
      break;
    case 'migrate':
      log('🚀 Running full migration...', 'blue');
      await runFullMigration({ question: () => Promise.resolve('yes') });
      break;
    case 'status':
      await checkStatus();
      break;
    case 'rollback':
      log('🔄 Running rollback...', 'blue');
      await runRollback({ question: () => Promise.resolve('yes') });
      break;
    case 'help':
    case '--help':
    case '-h':
      log('API Key Migration Tool', 'cyan');
      log('Usage: node run-migration.js [command]', 'blue');
      log('Commands:', 'blue');
      log('  dry-run    Run migration test without changes', 'cyan');
      log('  migrate    Run full migration', 'cyan');
      log('  status     Check migration status', 'cyan');
      log('  rollback   Remove migrated keys (testing only)', 'cyan');
      log('  help       Show this help message', 'cyan');
      log('  (no args)  Interactive mode', 'cyan');
      break;
    default:
      log(`❌ Unknown command: ${command}`, 'red');
      log('Use "help" for available commands', 'yellow');
  }
}

if (require.main === module) {
  handleCommandLine().catch(error => {
    log(`💥 Script failed: ${error.message}`, 'red');
    console.error(error);
    process.exit(1);
  });
}

module.exports = { 
  runDryRun, 
  runFullMigration, 
  checkStatus, 
  runRollback 
};