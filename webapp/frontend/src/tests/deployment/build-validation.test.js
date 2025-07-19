/**
 * Build Validation Tests
 * Tests that catch CI/CD and deployment issues before they reach AWS
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { spawn } from 'child_process';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

describe('Build Validation Tests', () => {
  const projectRoot = join(process.cwd());
  
  describe('Configuration Files', () => {
    it('should have valid package.json with correct module type', () => {
      const packagePath = join(projectRoot, 'package.json');
      expect(existsSync(packagePath)).toBe(true);
      
      const packageJson = JSON.parse(readFileSync(packagePath, 'utf8'));
      expect(packageJson.type).toBe('module');
      expect(packageJson.name).toBe('financial-dashboard-frontend');
    });

    it('should have PostCSS config with correct extension', () => {
      const cjsConfig = join(projectRoot, 'postcss.config.cjs');
      const jsConfig = join(projectRoot, 'postcss.config.js');
      
      // Should use .cjs extension for compatibility
      expect(existsSync(cjsConfig)).toBe(true);
      expect(existsSync(jsConfig)).toBe(false);
      
      const config = readFileSync(cjsConfig, 'utf8');
      expect(config).toContain('module.exports');
      expect(config).toContain('tailwindcss');
      expect(config).toContain('autoprefixer');
    });

    it('should have valid Vite config without deprecated imports', () => {
      const vitePath = join(projectRoot, 'vite.config.js');
      expect(existsSync(vitePath)).toBe(true);
      
      const viteConfig = readFileSync(vitePath, 'utf8');
      expect(viteConfig).toContain('export default defineConfig');
      expect(viteConfig).not.toContain('use-sync-external-store');
    });

    it('should have valid environment configuration', () => {
      const envProd = join(projectRoot, '.env.production');
      expect(existsSync(envProd)).toBe(true);
      
      const envContent = readFileSync(envProd, 'utf8');
      expect(envContent).toContain('VITE_API_URL');
    });
  });

  describe('Build Process', () => {
    let buildResult;
    
    beforeAll(async () => {
      // Run actual build to test for issues
      buildResult = await runBuild();
    }, 120000); // 2 minute timeout for build

    it('should build successfully without errors', () => {
      expect(buildResult.success).toBe(true);
      expect(buildResult.stderr).not.toContain('Error:');
      expect(buildResult.stderr).not.toContain('Failed to load');
    });

    it('should generate expected output files', () => {
      const distPath = join(projectRoot, 'dist');
      expect(existsSync(distPath)).toBe(true);
      
      const indexPath = join(distPath, 'index.html');
      expect(existsSync(indexPath)).toBe(true);
      
      // Check for CSS and JS assets
      const indexContent = readFileSync(indexPath, 'utf8');
      expect(indexContent).toMatch(/assets\/index-[a-zA-Z0-9]+\.css/);
      expect(indexContent).toMatch(/assets\/index-[a-zA-Z0-9]+\.js/);
    });

    it('should not expose sensitive information in build output', () => {
      const distPath = join(projectRoot, 'dist');
      const sensitivePatterns = [
        /AKIA[0-9A-Z]{16}/, // AWS access keys
        /[A-Za-z0-9/+=]{40}/, // AWS secret keys
        /pk_live_[a-zA-Z0-9]{24}/, // Stripe live keys
        /sk_live_[a-zA-Z0-9]{24}/, // Stripe secret keys
      ];

      // Check built files for sensitive data
      checkDistFilesForSensitiveData(distPath, sensitivePatterns);
    });

    it('should have reasonable bundle sizes', () => {
      expect(buildResult.bundleInfo.vendor).toBeLessThan(800 * 1024); // 800KB
      expect(buildResult.bundleInfo.main).toBeLessThan(100 * 1024); // 100KB
    });
  });

  describe('ES Module Compatibility', () => {
    it('should handle dynamic imports correctly', async () => {
      // Test that our dynamic import strategy works
      const mainJsx = join(projectRoot, 'src/main.jsx');
      const content = readFileSync(mainJsx, 'utf8');
      
      // Should use dynamic imports for testing framework
      expect(content).toContain('import(');
      expect(content).toContain('automatedTestFramework');
      expect(content).not.toContain('import automatedTestFramework');
    });

    it('should not have CommonJS syntax in ES modules', () => {
      const srcFiles = getJavaScriptFiles(join(projectRoot, 'src'));
      
      srcFiles.forEach(file => {
        const content = readFileSync(file, 'utf8');
        const fileName = file.split('/').pop();
        
        // Skip test files and certain utility files
        if (fileName.endsWith('.test.js') || fileName.includes('secureLogger')) {
          return;
        }
        
        expect(content).not.toContain('module.exports');
        expect(content).not.toContain('require(');
      });
    });
  });

  describe('Dependency Validation', () => {
    it('should not have conflicting React versions', () => {
      const packageJson = JSON.parse(readFileSync(join(projectRoot, 'package.json'), 'utf8'));
      
      // Check for use-sync-external-store conflicts
      expect(packageJson.dependencies).not.toHaveProperty('use-sync-external-store');
      expect(packageJson.overrides).not.toHaveProperty('use-sync-external-store');
    });

    it('should have required testing dependencies', () => {
      const packageJson = JSON.parse(readFileSync(join(projectRoot, 'package.json'), 'utf8'));
      
      expect(packageJson.devDependencies).toHaveProperty('vitest');
      expect(packageJson.devDependencies).toHaveProperty('@playwright/test');
      expect(packageJson.devDependencies).toHaveProperty('artillery');
    });
  });
});

// Helper functions
function runBuild() {
  return new Promise((resolve) => {
    const build = spawn('npm', ['run', 'build'], {
      cwd: process.cwd(),
      stdio: ['pipe', 'pipe', 'pipe']
    });

    let stdout = '';
    let stderr = '';
    let bundleInfo = {};

    build.stdout.on('data', (data) => {
      stdout += data.toString();
      
      // Parse bundle size information
      const lines = data.toString().split('\n');
      lines.forEach(line => {
        if (line.includes('vendor-') && line.includes('kB')) {
          const match = line.match(/(\d+\.?\d*)\s*kB/);
          if (match) bundleInfo.vendor = parseFloat(match[1]) * 1024;
        }
        if (line.includes('index-') && line.includes('kB')) {
          const match = line.match(/(\d+\.?\d*)\s*kB/);
          if (match) bundleInfo.main = parseFloat(match[1]) * 1024;
        }
      });
    });

    build.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    build.on('close', (code) => {
      resolve({
        success: code === 0,
        stdout,
        stderr,
        bundleInfo,
        exitCode: code
      });
    });
  });
}

function checkDistFilesForSensitiveData(distPath, patterns) {
  const files = getJavaScriptFiles(distPath);
  
  files.forEach(file => {
    const content = readFileSync(file, 'utf8');
    
    patterns.forEach(pattern => {
      expect(content).not.toMatch(pattern);
    });
  });
}

function getJavaScriptFiles(dir) {
  const fs = require('fs');
  const path = require('path');
  
  const files = [];
  
  function walk(currentDir) {
    const items = fs.readdirSync(currentDir);
    
    items.forEach(item => {
      const fullPath = path.join(currentDir, item);
      const stat = fs.statSync(fullPath);
      
      if (stat.isDirectory()) {
        walk(fullPath);
      } else if (item.endsWith('.js') || item.endsWith('.jsx')) {
        files.push(fullPath);
      }
    });
  }
  
  walk(dir);
  return files;
}