/**
 * Deployment Validation Tests
 * 
 * These tests validate that the deployment environment requirements are met
 * and catch issues that would cause CI/CD failures before they reach the pipeline.
 */

import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

describe('Deployment Validation Tests', () => {
  describe('Package Management', () => {
    test('package-lock.json should be in sync with package.json', () => {
      // This test prevents the "npm ci" sync error we encountered
      expect(() => {
        execSync('npm ci --dry-run', { 
          stdio: 'pipe',
          cwd: process.cwd()
        });
      }).not.toThrow();
    });

    test('all dependencies should be resolvable', () => {
      const packageJson = JSON.parse(
        fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf8')
      );
      
      const packageLockExists = fs.existsSync(
        path.join(process.cwd(), 'package-lock.json')
      );
      
      expect(packageLockExists).toBe(true);
      
      if (packageLockExists) {
        const packageLock = JSON.parse(
          fs.readFileSync(path.join(process.cwd(), 'package-lock.json'), 'utf8')
        );
        
        // Validate package.json name matches package-lock.json
        expect(packageLock.name).toBe(packageJson.name);
        expect(packageLock.version).toBe(packageJson.version);
      }
    });

    test('critical dependencies should be present in lock file', () => {
      const packageLock = JSON.parse(
        fs.readFileSync(path.join(process.cwd(), 'package-lock.json'), 'utf8')
      );
      
      // Check for dependencies that have caused deployment failures
      const criticalDeps = [
        'react',
        'react-dom',
        'vite',
        '@vitejs/plugin-react'
      ];
      
      criticalDeps.forEach(dep => {
        expect(packageLock.packages).toHaveProperty(`node_modules/${dep}`);
      });
    });
  });

  describe('Build Environment', () => {
    test('build should complete successfully', () => {
      expect(() => {
        execSync('npm run build', { 
          stdio: 'pipe',
          cwd: process.cwd(),
          timeout: 60000 // 60 second timeout
        });
      }).not.toThrow();
    });

    test('Node.js version should be compatible', () => {
      const nodeVersion = process.version;
      const versionParts = nodeVersion.slice(1).split('.').map(Number);
      const [major, minor] = versionParts;
      
      // Requires Node 20.19+ or 22.12+
      const isCompatible = 
        (major === 20 && minor >= 19) || 
        (major === 22 && minor >= 12) || 
        (major > 22);
      
      expect(isCompatible).toBe(true);
    });

    test('essential scripts should be defined', () => {
      const packageJson = JSON.parse(
        fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf8')
      );
      
      const requiredScripts = ['build', 'dev', 'test'];
      
      requiredScripts.forEach(script => {
        expect(packageJson.scripts).toHaveProperty(script);
        expect(typeof packageJson.scripts[script]).toBe('string');
        expect(packageJson.scripts[script].length).toBeGreaterThan(0);
      });
    });
  });

  describe('File System Dependencies', () => {
    test('essential configuration files should exist', () => {
      const requiredFiles = [
        'vite.config.js',
        'package.json',
        'package-lock.json'
      ];
      
      requiredFiles.forEach(file => {
        const filePath = path.join(process.cwd(), file);
        expect(fs.existsSync(filePath)).toBe(true);
      });
    });

    test('source directory structure should be valid', () => {
      const requiredDirs = [
        'src',
        'src/components',
        'src/pages',
        'src/services'
      ];
      
      requiredDirs.forEach(dir => {
        const dirPath = path.join(process.cwd(), dir);
        expect(fs.existsSync(dirPath)).toBe(true);
        expect(fs.statSync(dirPath).isDirectory()).toBe(true);
      });
    });
  });

  describe('CI/CD Compatibility', () => {
    test('clean install should work in fresh environment', () => {
      // Simulate CI environment where node_modules doesn't exist
      const nodeModulesPath = path.join(process.cwd(), 'node_modules');
      const nodeModulesExists = fs.existsSync(nodeModulesPath);
      
      if (nodeModulesExists) {
        // Test that we can reinstall from scratch
        expect(() => {
          execSync('npm ci --prefer-offline', { 
            stdio: 'pipe',
            cwd: process.cwd()
          });
        }).not.toThrow();
      }
    });

    test('production build should work without dev dependencies', () => {
      // This simulates the production build environment
      expect(() => {
        execSync('NODE_ENV=production npm run build', { 
          stdio: 'pipe',
          cwd: process.cwd(),
          timeout: 60000
        });
      }).not.toThrow();
    });
  });
});