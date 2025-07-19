/**
 * CI/CD Deployment Validation Tests
 * Catches deployment-specific issues that only appear in CI environments
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { spawn } from 'child_process';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

// Use current working directory as project root
const projectRoot = '.';

describe('CI/CD Deployment Validation', () => {
  
  describe('Configuration File Compatibility', () => {
    it('should have PostCSS config compatible with both ES modules and CommonJS', () => {
      const cjsConfig = join(projectRoot, 'postcss.config.cjs');
      const jsConfig = join(projectRoot, 'postcss.config.js');
      
      // Should prefer .cjs for CI compatibility
      expect(existsSync(cjsConfig)).toBe(true);
      
      if (existsSync(cjsConfig)) {
        const config = readFileSync(cjsConfig, 'utf8');
        expect(config).toContain('module.exports');
        expect(config).not.toContain('export default');
      }
      
      // Should not have conflicting .js file when using type: "module"
      if (existsSync(jsConfig)) {
        const config = readFileSync(jsConfig, 'utf8');
        // If .js exists, it should use ES modules
        expect(config).toContain('export default');
      }
    });

    it('should have package.json configured for ES modules', () => {
      const packagePath = join(projectRoot, 'package.json');
      const packageJson = JSON.parse(readFileSync(packagePath, 'utf8'));
      
      expect(packageJson.type).toBe('module');
      expect(packageJson.name).toBe('financial-dashboard-frontend');
    });

    it('should have Vite config without deprecated imports', () => {
      const vitePath = join(projectRoot, 'vite.config.js');
      const viteConfig = readFileSync(vitePath, 'utf8');
      
      // Should not have problematic alias
      expect(viteConfig).not.toContain('use-sync-external-store/shim');
    });
  });

  describe('Build Process Validation', () => {
    let buildOutput;
    
    beforeAll(async () => {
      buildOutput = await runBuildProcess();
    }, 180000); // 3 minute timeout

    it('should complete build without PostCSS errors', () => {
      expect(buildOutput.success).toBe(true);
      expect(buildOutput.stderr).not.toContain('Failed to load PostCSS config');
      expect(buildOutput.stderr).not.toContain('Unexpected token');
      expect(buildOutput.stderr).not.toContain('module is not defined');
    });

    it('should not have ES module conflicts', () => {
      expect(buildOutput.stderr).not.toContain('Cannot use import statement outside a module');
      expect(buildOutput.stderr).not.toContain('require is not defined');
      expect(buildOutput.stderr).not.toContain('module is not defined in ES module scope');
    });

    it('should handle Chart.js migration properly', () => {
      expect(buildOutput.stderr).not.toContain('Chart.js');
      expect(buildOutput.stderr).not.toContain('react-chartjs-2');
      // Should use recharts instead
      expect(buildOutput.stdout).toContain('recharts');
    });

    it('should have MUI icons properly configured', () => {
      expect(buildOutput.stderr).not.toContain('Trading');
      expect(buildOutput.stderr).not.toContain('icon not found');
    });
  });

  describe('GitHub Actions Environment Simulation', () => {
    it('should work with GitHub Actions Node.js environment', async () => {
      // Simulate GitHub Actions environment variables
      const originalCI = process.env.CI;
      const originalGithubActions = process.env.GITHUB_ACTIONS;
      
      process.env.CI = 'true';
      process.env.GITHUB_ACTIONS = 'true';
      
      try {
        const result = await runPostCSSValidation();
        expect(result.success).toBe(true);
      } finally {
        // Restore original environment
        if (originalCI !== undefined) {
          process.env.CI = originalCI;
        } else {
          delete process.env.CI;
        }
        
        if (originalGithubActions !== undefined) {
          process.env.GITHUB_ACTIONS = originalGithubActions;
        } else {
          delete process.env.GITHUB_ACTIONS;
        }
      }
    });

    it('should handle different Node.js versions', async () => {
      // Test compatibility with different Node.js versions
      const nodeVersion = process.version;
      console.log(`Testing with Node.js version: ${nodeVersion}`);
      
      // Should work with Node 18+ (current CI standard)
      const majorVersion = parseInt(nodeVersion.slice(1).split('.')[0]);
      expect(majorVersion).toBeGreaterThanOrEqual(18);
    });
  });

  describe('Dependency Compatibility', () => {
    it('should not have conflicting React versions', () => {
      const packageJson = JSON.parse(readFileSync(join(projectRoot, 'package.json'), 'utf8'));
      
      // Should not have use-sync-external-store conflicts
      expect(packageJson.dependencies).not.toHaveProperty('use-sync-external-store');
      expect(packageJson.overrides).not.toHaveProperty('use-sync-external-store');
    });

    it('should have testing dependencies compatible with Node 18', () => {
      const packageJson = JSON.parse(readFileSync(join(projectRoot, 'package.json'), 'utf8'));
      
      // Should have Playwright (works with Node 18)
      expect(packageJson.devDependencies).toHaveProperty('@playwright/test');
      
      // Should have Vitest (works with Node 18)
      expect(packageJson.devDependencies).toHaveProperty('vitest');
      
      // Artillery 2.0.23 should work with Node 18
      expect(packageJson.devDependencies).toHaveProperty('artillery');
    });
  });

  describe('Runtime Configuration', () => {
    it('should have proper environment detection', () => {
      const isDev = import.meta.env.DEV;
      const isProd = import.meta.env.PROD;
      
      // Should be either dev or prod, not both
      expect(isDev !== isProd).toBe(true);
    });

    it('should have build-time configuration available', () => {
      // Config should be generated at build time
      const configPath = join(projectRoot, 'public/config.js');
      
      if (existsSync(configPath)) {
        const config = readFileSync(configPath, 'utf8');
        expect(config).toContain('window.__CONFIG__');
        expect(config).toContain('API_URL');
      }
    });
  });

  describe('Security in CI Environment', () => {
    it('should not expose sensitive data in build output', () => {
      // Check for API keys in build output
      expect(buildOutput.stdout).not.toMatch(/AKIA[0-9A-Z]{16}/); // AWS access keys
      expect(buildOutput.stdout).not.toMatch(/[A-Za-z0-9/+=]{40}/); // AWS secrets
      expect(buildOutput.stdout).not.toMatch(/pk_live_[a-zA-Z0-9]{24}/); // Stripe keys
    });

    it('should not have hardcoded secrets in configuration files', () => {
      const configFiles = [
        'vite.config.js',
        '.env.production',
        'public/config.js'
      ];
      
      configFiles.forEach(configFile => {
        const filePath = join(projectRoot, configFile);
        if (existsSync(filePath)) {
          const content = readFileSync(filePath, 'utf8');
          
          // Should not contain actual secrets
          expect(content).not.toMatch(/AKIA[0-9A-Z]{16}/);
          expect(content).not.toMatch(/rds-db-credentials/);
          expect(content).not.toMatch(/secret-[a-z0-9]{32}/);
        }
      });
    });
  });
});

// Helper functions
function runBuildProcess() {
  return new Promise((resolve) => {
    const build = spawn('npm', ['run', 'build'], {
      cwd: projectRoot,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, CI: 'true' } // Simulate CI environment
    });

    let stdout = '';
    let stderr = '';

    build.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    build.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    build.on('close', (code) => {
      resolve({
        success: code === 0,
        stdout,
        stderr,
        exitCode: code
      });
    });

    // Timeout after 3 minutes
    setTimeout(() => {
      build.kill();
      resolve({
        success: false,
        stdout,
        stderr: stderr + '\nBuild timed out after 3 minutes',
        exitCode: -1
      });
    }, 180000);
  });
}

function runPostCSSValidation() {
  return new Promise((resolve) => {
    const test = spawn('npx', ['postcss', '--version'], {
      cwd: projectRoot,
      stdio: ['pipe', 'pipe', 'pipe']
    });

    let output = '';
    let errorOutput = '';

    test.stdout.on('data', (data) => {
      output += data.toString();
    });

    test.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    test.on('close', (code) => {
      resolve({
        success: code === 0,
        output,
        errorOutput
      });
    });
  });
}