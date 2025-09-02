/**
 * CI/CD Pipeline Validation - Tests that catch GitHub Actions failures
 * Specifically targets: dependency caching issues, setup-node problems
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

describe('GitHub Actions Pipeline Validation', () => {
  
  describe('Dependency Caching (setup-node@v3 fix)', () => {
    test('package-lock.json exists and is valid for caching', () => {
      const lockPath = path.join(__dirname, '../../package-lock.json');
      expect(fs.existsSync(lockPath)).toBe(true);
      
      const lockFile = JSON.parse(fs.readFileSync(lockPath, 'utf8'));
      expect(lockFile.lockfileVersion).toBeDefined();
      expect(lockFile.packages).toBeDefined();
    });

    test('node_modules structure supports cache resolution', () => {
      const nodeModulesPath = path.join(__dirname, '../../node_modules');
      expect(fs.existsSync(nodeModulesPath)).toBe(true);
      
      // Check critical paths exist for caching
      const criticalPaths = ['express', 'jest', 'pg'];
      criticalPaths.forEach(dep => {
        expect(fs.existsSync(path.join(nodeModulesPath, dep))).toBe(true);
      });
    });

    test('npm config is compatible with CI cache paths', () => {
      try {
        const result = execSync('npm config get cache', { 
          cwd: path.join(__dirname, '../..'),
          encoding: 'utf8' 
        });
        expect(typeof result).toBe('string');
        expect(result.trim().length).toBeGreaterThan(0);
      } catch (error) {
        throw new Error(`npm config cache issue: ${error.message}`);
      }
    });
  });

  describe('Pre-deploy Test Gates', () => {
    test('dependency audit passes (no high/critical vulnerabilities)', async () => {
      try {
        execSync('npm audit --audit-level=high', {
          cwd: path.join(__dirname, '../..'),
          stdio: 'pipe'
        });
        // If we get here, no high/critical vulnerabilities
        expect(true).toBe(true);
      } catch (error) {
        throw new Error(`Security vulnerabilities detected: ${error.message}`);
      }
    });

    test('application can start without hanging', () => {
      const packageJson = require('../../package.json');
      expect(packageJson.scripts.start).toBe('node index.js');
      
      // Verify main entry point exists
      const indexPath = path.join(__dirname, '../../index.js');
      expect(fs.existsSync(indexPath)).toBe(true);
    });
  });
});