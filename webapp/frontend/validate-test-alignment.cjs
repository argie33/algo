#!/usr/bin/env node
/**
 * Test Alignment Validator
 * Ensures all test levels use consistent data from loader scripts
 */

const fs = require('fs');
const path = require('path');

// Expected values from loader scripts
const LOADER_SCHEMA_VALUES = {
  portfolio: {
    total_value: 1250000,
    daily_pnl: 3200,
    total_pnl: 92000
  },
  stocks: {
    AAPL: { price: 195.12, volume: 52840000 },
    MSFT: { price: 415.20, volume: 28450000 },
    GOOGL: { price: 147.65, volume: 31200000 }
  },
  user: {
    id: "test-user-123",
    email: "test@example.com"
  }
};

// UI Display expectations
const EXPECTED_UI_VALUES = {
  portfolioValue: "$1,250,000",
  portfolioValueRaw: "1,250,000",
  dailyPnL: "$3,200",
  applePrice: "$195.12",
  microsoftPrice: "$415.20",
  googlePrice: "$147.65"
};

class TestAlignmentValidator {
  constructor() {
    this.errors = [];
    this.warnings = [];
    this.checks = 0;
  }

  validateFile(filePath, content) {
    this.checks++;
    const fileName = path.basename(filePath);

    // Check for old values that should be updated
    if (content.includes('totalValue: 100000') && !content.includes('totalValue: 1000000000')) {
      this.errors.push(`${fileName}: Still uses old totalValue: 100000 (should be total_value: 1250000)`);
    }

    if (content.includes('186.75') && !fileName.includes('historical')) {
      this.errors.push(`${fileName}: Still uses old AAPL price 186.75 (should be 195.12)`);
    }

    if (content.includes('411.25') && !fileName.includes('historical')) {
      this.errors.push(`${fileName}: Still uses old MSFT price 411.25 (should be 415.20)`);
    }

    // Check for correct schema field names
    if (content.includes('totalValue') && content.includes('test')) {
      this.warnings.push(`${fileName}: Uses camelCase 'totalValue' (loader schema uses 'total_value')`);
    }

    // Check for correct portfolio value
    if (content.includes('1,250,000') || content.includes('1250000')) {
      console.log(`✅ ${fileName}: Uses correct portfolio value`);
    }

    // Check for loader-aligned stock prices
    if (content.includes('195.12')) {
      console.log(`✅ ${fileName}: Uses correct AAPL price from loader`);
    }

    if (content.includes('415.20')) {
      console.log(`✅ ${fileName}: Uses correct MSFT price from loader`);
    }

    if (content.includes('147.65')) {
      console.log(`✅ ${fileName}: Uses correct GOOGL price from loader`);
    }
  }

  scanDirectory(dir, extensions = ['.test.jsx', '.test.js', '.sql']) {
    const files = fs.readdirSync(dir, { withFileTypes: true });

    for (const file of files) {
      const fullPath = path.join(dir, file.name);

      if (file.isDirectory() && !file.name.includes('node_modules')) {
        this.scanDirectory(fullPath, extensions);
      } else if (extensions.some(ext => file.name.endsWith(ext))) {
        try {
          const content = fs.readFileSync(fullPath, 'utf8');
          this.validateFile(fullPath, content);
        } catch (err) {
          this.warnings.push(`Could not read ${fullPath}: ${err.message}`);
        }
      }
    }
  }

  generateReport() {
    console.log('\n=== TEST ALIGNMENT VALIDATION REPORT ===\n');

    console.log(`📊 Checked ${this.checks} files\n`);

    if (this.errors.length === 0) {
      console.log('✅ NO CRITICAL ALIGNMENT ERRORS FOUND!\n');
    } else {
      console.log('❌ CRITICAL ALIGNMENT ERRORS:\n');
      this.errors.forEach(error => console.log(`  • ${error}`));
      console.log('');
    }

    if (this.warnings.length > 0) {
      console.log('⚠️  WARNINGS:\n');
      this.warnings.forEach(warning => console.log(`  • ${warning}`));
      console.log('');
    }

    console.log('🎯 LOADER SCHEMA VALUES (SOURCE OF TRUTH):');
    console.log('  Portfolio total_value:', LOADER_SCHEMA_VALUES.portfolio.total_value);
    console.log('  Portfolio daily_pnl:', LOADER_SCHEMA_VALUES.portfolio.daily_pnl);
    console.log('  AAPL price:', LOADER_SCHEMA_VALUES.stocks.AAPL.price);
    console.log('  MSFT price:', LOADER_SCHEMA_VALUES.stocks.MSFT.price);
    console.log('  GOOGL price:', LOADER_SCHEMA_VALUES.stocks.GOOGL.price);
    console.log('');

    console.log('📱 EXPECTED UI VALUES:');
    console.log('  Portfolio display:', EXPECTED_UI_VALUES.portfolioValue);
    console.log('  Daily PnL display:', EXPECTED_UI_VALUES.dailyPnL);
    console.log('  AAPL display:', EXPECTED_UI_VALUES.applePrice);
    console.log('');

    if (this.errors.length === 0 && this.warnings.length === 0) {
      console.log('🎉 ALL TESTS ARE PROPERLY ALIGNED WITH LOADER SCHEMA!');
      process.exit(0);
    } else if (this.errors.length > 0) {
      console.log('💥 CRITICAL ERRORS FOUND - TESTS ARE NOT ALIGNED!');
      process.exit(1);
    } else {
      console.log('⚠️  WARNINGS FOUND - REVIEW RECOMMENDED');
      process.exit(0);
    }
  }
}

// Run validation
const validator = new TestAlignmentValidator();

console.log('🔍 Scanning test files for alignment with loader schema...\n');

// Scan all test directories
validator.scanDirectory('/home/stocks/algo/webapp/frontend/src/tests');
validator.scanDirectory('/home/stocks/algo/webapp/lambda/tests');
validator.scanDirectory('/home/stocks/algo/webapp/lambda/scripts');

validator.generateReport();