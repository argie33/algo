#!/usr/bin/env node
/**
 * 🧹 COMPLETE TEST CONSOLIDATION SCRIPT
 * 
 * This script finds and consolidates ALL testing assets from across the entire project
 * into one cohesive, enterprise-grade testing structure.
 */

import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

class TestConsolidator {
  constructor() {
    this.projectRoot = '/home/stocks/algo';
    this.targetDir = path.join(__dirname);
    this.discoveredTests = {
      files: [],
      configs: [],
      directories: []
    };
    this.consolidationMap = new Map();
    this.setupConsolidationMap();
  }

  setupConsolidationMap() {
    // Map source patterns to target directories
    this.consolidationMap.set(/.*\/frontend\/.*component.*test/, 'unit/components');
    this.consolidationMap.set(/.*\/frontend\/.*service.*test/, 'unit/services');
    this.consolidationMap.set(/.*\/frontend\/.*util.*test/, 'unit/utils');
    this.consolidationMap.set(/.*\/frontend\/.*hook.*test/, 'unit/hooks');
    this.consolidationMap.set(/.*\/frontend\/.*context.*test/, 'unit/contexts');
    
    this.consolidationMap.set(/.*\/lambda\/tests\/unit/, 'unit/services');
    this.consolidationMap.set(/.*\/lambda\/tests\/integration/, 'integration/backend');
    this.consolidationMap.set(/.*\/lambda\/.*api.*test/, 'integration/api');
    this.consolidationMap.set(/.*\/lambda\/.*database.*test/, 'integration/database');
    this.consolidationMap.set(/.*\/lambda\/.*auth.*test/, 'integration/middleware');
    
    this.consolidationMap.set(/.*\/e2e-testing\/tests/, 'e2e/workflows');
    this.consolidationMap.set(/.*auth.*spec/, 'e2e/auth');
    this.consolidationMap.set(/.*portfolio.*spec/, 'e2e/portfolio');
    this.consolidationMap.set(/.*trading.*spec/, 'e2e/trading');
    this.consolidationMap.set(/.*market.*spec/, 'e2e/market');
    
    this.consolidationMap.set(/.*performance.*test/, 'performance/load');
    this.consolidationMap.set(/.*security.*test/, 'security/compliance');
    this.consolidationMap.set(/.*compliance.*test/, 'security/owasp');
    
    this.consolidationMap.set(/.*config/, 'config/runners');
    this.consolidationMap.set(/.*setup/, 'config/environments');
  }

  async consolidateAll() {
    console.log('🧹 COMPLETE TEST CONSOLIDATION');
    console.log('═'.repeat(60));
    
    // 1. Discover all test assets
    await this.discoverAllTests();
    
    // 2. Analyze and categorize
    await this.categorizeTests();
    
    // 3. Copy and organize files
    await this.copyAndOrganizeFiles();
    
    // 4. Create unified configurations
    await this.createUnifiedConfigs();
    
    // 5. Generate documentation
    await this.generateConsolidationReport();
    
    console.log('✅ Test consolidation complete!');
  }

  async discoverAllTests() {
    console.log('🔍 Discovering all test assets...');
    
    const testPatterns = [
      '**/*test*.js',
      '**/*test*.jsx', 
      '**/*spec*.js',
      '**/*spec*.jsx',
      '**/jest.config.js',
      '**/vitest.config.js',
      '**/playwright.config.js',
      '**/test-*.js',
      '**/setup.js'
    ];

    // Search from project root
    await this.searchDirectory(this.projectRoot, testPatterns);
    
    console.log(`📊 Discovered: ${this.discoveredTests.files.length} files, ${this.discoveredTests.configs.length} configs`);
  }

  async searchDirectory(dir, patterns) {
    try {
      const entries = await fs.readdir(dir, { withFileTypes: true });
      
      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        
        // Skip node_modules and .git
        if (entry.name === 'node_modules' || entry.name === '.git') continue;
        
        if (entry.isDirectory()) {
          if (entry.name.includes('test')) {
            this.discoveredTests.directories.push(fullPath);
          }
          await this.searchDirectory(fullPath, patterns);
        } else if (entry.isFile()) {
          if (this.matchesPattern(entry.name, patterns)) {
            const category = this.categorizeFile(fullPath);
            this.discoveredTests.files.push({
              path: fullPath,
              name: entry.name,
              category,
              size: (await fs.stat(fullPath)).size
            });
          }
        }
      }
    } catch (error) {
      // Skip directories we can't read
    }
  }

  matchesPattern(filename, patterns) {
    return patterns.some(pattern => {
      const regex = new RegExp(pattern.replace(/\*\*/g, '.*').replace(/\*/g, '[^/]*'));
      return regex.test(filename);
    });
  }

  categorizeFile(filePath) {
    for (const [pattern, category] of this.consolidationMap.entries()) {
      if (pattern.test(filePath)) {
        return category;
      }
    }
    
    // Default categorization based on file content/location
    if (filePath.includes('component')) return 'unit/components';
    if (filePath.includes('service')) return 'unit/services';
    if (filePath.includes('util')) return 'unit/utils';
    if (filePath.includes('api')) return 'integration/api';
    if (filePath.includes('database')) return 'integration/database';
    if (filePath.includes('e2e') || filePath.includes('spec')) return 'e2e/workflows';
    if (filePath.includes('performance')) return 'performance/load';
    if (filePath.includes('security')) return 'security/compliance';
    if (filePath.includes('config')) return 'config/runners';
    
    return 'misc'; // For manual review
  }

  async categorizeTests() {
    console.log('📋 Categorizing tests...');
    
    const categories = {};
    this.discoveredTests.files.forEach(file => {
      if (!categories[file.category]) {
        categories[file.category] = [];
      }
      categories[file.category].push(file);
    });

    console.log('📊 Test distribution:');
    Object.entries(categories).forEach(([category, files]) => {
      console.log(`  ${category}: ${files.length} files`);
    });
  }

  async copyAndOrganizeFiles() {
    console.log('📁 Copying and organizing files...');
    
    const copied = [];
    const skipped = [];
    
    for (const file of this.discoveredTests.files) {
      try {
        if (file.category === 'misc') {
          skipped.push(file);
          continue;
        }

        const targetDir = path.join(this.targetDir, file.category);
        await fs.mkdir(targetDir, { recursive: true });
        
        const targetPath = path.join(targetDir, file.name);
        
        // Check if file already exists
        try {
          await fs.access(targetPath);
          console.log(`  ⚠️  Skipping duplicate: ${file.name}`);
          continue;
        } catch {
          // File doesn't exist, proceed with copy
        }
        
        await fs.copyFile(file.path, targetPath);
        copied.push({ from: file.path, to: targetPath });
        
      } catch (error) {
        console.error(`❌ Failed to copy ${file.path}:`, error.message);
      }
    }
    
    console.log(`✅ Copied ${copied.length} files, skipped ${skipped.length} files`);
  }

  async createUnifiedConfigs() {
    console.log('⚙️ Creating unified configurations...');
    
    // Unified package.json for all testing
    const unifiedPackage = {
      name: "@financial-dashboard/testing",
      version: "1.0.0",
      description: "Enterprise testing framework for Financial Dashboard",
      scripts: {
        "test": "node test-master.js",
        "test:unit": "node test-master.js --category=unit",
        "test:integration": "node test-master.js --category=integration", 
        "test:e2e": "node test-master.js --category=e2e",
        "test:security": "node test-master.js --category=security",
        "test:performance": "node test-master.js --category=performance",
        "test:all": "node test-master.js --category=all",
        "test:ci": "node test-master.js --ci",
        "test:compliance": "node test-master.js --compliance",
        "test:watch": "node test-master.js --watch",
        "test:coverage": "node test-master.js --coverage",
        "test:report": "node scripts/runners/generate-report.js"
      },
      dependencies: {
        "@playwright/test": "^1.40.0",
        "@testing-library/react": "^13.4.0",
        "@testing-library/jest-dom": "^5.16.5",
        "@testing-library/user-event": "^14.4.3",
        "vitest": "^1.0.0",
        "jest": "^29.0.0",
        "axe-core": "^4.7.0",
        "artillery": "^2.0.0"
      }
    };

    await fs.writeFile(
      path.join(this.targetDir, 'package.json'),
      JSON.stringify(unifiedPackage, null, 2)
    );

    // Unified vitest config
    const vitestConfig = `
import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./config/environments/test-setup.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      reportsDirectory: './reports/coverage',
      exclude: [
        'node_modules/',
        'test-results/',
        'reports/',
        'config/',
        '**/*.{test,spec}.{js,jsx,ts,tsx}'
      ],
      thresholds: {
        global: {
          statements: 85,
          branches: 80,
          functions: 85,
          lines: 85
        }
      }
    },
    testTimeout: 30000,
    hookTimeout: 10000
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, '../../../src'),
      '@tests': resolve(__dirname, '.')
    }
  }
});`;

    await fs.writeFile(
      path.join(this.targetDir, 'vitest.config.js'),
      vitestConfig
    );
  }

  async generateConsolidationReport() {
    const report = {
      timestamp: new Date().toISOString(),
      summary: {
        totalFilesDiscovered: this.discoveredTests.files.length,
        totalConfigsFound: this.discoveredTests.configs.length,
        totalDirectoriesFound: this.discoveredTests.directories.length
      },
      filesByCategory: {},
      consolidationActions: [],
      recommendations: [
        '🧹 Remove old scattered test directories after validation',
        '⚙️ Update CI/CD pipelines to use new test structure',
        '📚 Update team documentation with new test commands',
        '🔄 Migrate any custom test utilities to helpers/',
        '📊 Review and merge duplicate test cases'
      ]
    };

    // Group files by category
    this.discoveredTests.files.forEach(file => {
      if (!report.filesByCategory[file.category]) {
        report.filesByCategory[file.category] = [];
      }
      report.filesByCategory[file.category].push({
        name: file.name,
        originalPath: file.path,
        size: file.size
      });
    });

    await fs.mkdir(path.join(this.targetDir, 'reports'), { recursive: true });
    await fs.writeFile(
      path.join(this.targetDir, 'reports/consolidation-report.json'),
      JSON.stringify(report, null, 2)
    );

    console.log('\n📋 CONSOLIDATION REPORT');
    console.log('-'.repeat(40));
    console.log(`Total files processed: ${report.summary.totalFilesDiscovered}`);
    console.log(`Files by category:`);
    Object.entries(report.filesByCategory).forEach(([category, files]) => {
      console.log(`  ${category}: ${files.length} files`);
    });
    console.log(`\n📊 Report saved: reports/consolidation-report.json`);
  }
}

// Run consolidation
const consolidator = new TestConsolidator();
consolidator.consolidateAll().catch(console.error);