#!/usr/bin/env node

/**
 * SIMPLE DEBUGGING - No browser dependencies
 * Uses basic HTTP requests to analyze the site
 */

import { readFile } from 'fs/promises';
import { createServer } from 'http';
import { parse } from 'url';
import path from 'path';

class SimpleDebugger {
  constructor() {
    this.errors = [];
    this.findings = [];
  }

  async analyzeBuildFiles() {
    console.log('🔍 ANALYZING BUILD FILES...');
    console.log('========================================');
    
    try {
      // Check index.html
      const indexPath = '/home/stocks/algo/webapp/frontend/dist/index.html';
      const indexContent = await readFile(indexPath, 'utf8');
      
      // Look for shim references
      if (indexContent.includes('use-sync-external-store-shim')) {
        this.errors.push({
          type: 'shim_reference_in_html',
          message: 'Found shim reference in index.html',
          file: 'dist/index.html'
        });
        console.log('🚨 FOUND: Shim reference in index.html');
      } else {
        console.log('✅ No shim references in index.html');
      }
      
      // Check main JS file
      const jsMatch = indexContent.match(/src="([^"]*index-[^"]*\.js)"/);
      if (jsMatch) {
        const jsFile = jsMatch[1].replace('/', '');
        const jsPath = `/home/stocks/algo/webapp/frontend/dist/${jsFile}`;
        
        try {
          console.log(`📄 Checking ${jsFile}...`);
          const jsContent = await readFile(jsPath, 'utf8');
          
          if (jsContent.includes('use-sync-external-store-shim.production.js')) {
            this.errors.push({
              type: 'exact_shim_reference',
              message: 'FOUND EXACT SHIM FILE REFERENCE!',
              file: jsFile,
              line: 'Searching...'
            });
            console.log('🎯 FOUND: Exact shim file reference in main JS!');
            
            // Find the line
            const lines = jsContent.split('\n');
            lines.forEach((line, index) => {
              if (line.includes('use-sync-external-store-shim.production.js')) {
                console.log(`📍 Line ${index + 1}: ${line.substring(0, 100)}...`);
                this.errors[this.errors.length - 1].line = index + 1;
                this.errors[this.errors.length - 1].content = line.substring(0, 200);
              }
            });
          } else {
            console.log('✅ No exact shim references in main JS');
          }
          
          // Check for other patterns
          if (jsContent.includes('useSyncExternalStore')) {
            console.log('📝 Found useSyncExternalStore usage (normal)');
          }
          
          if (jsContent.includes('useState')) {
            console.log('📝 Found useState usage (normal)');
          }
          
        } catch (err) {
          console.log(`❌ Could not read JS file: ${err.message}`);
        }
      }
      
      // Check cache bust file
      try {
        const cacheBustContent = await readFile('/home/stocks/algo/webapp/frontend/cache_bust.txt', 'utf8');
        console.log(`🔄 Cache bust version: ${cacheBustContent.trim()}`);
      } catch (err) {
        console.log('❓ No cache bust file found');
      }
      
    } catch (error) {
      console.error('❌ Error analyzing build files:', error.message);
    }
  }

  async testServerResponse() {
    console.log('\n🌐 TESTING SERVER RESPONSES...');
    console.log('========================================');
    
    const testUrls = [
      'http://localhost:8080/',
      'http://localhost:8080/assets/index-DSAigFlh.js',
      'http://localhost:8080/use-sync-external-store-shim.production.js',
      'http://localhost:8080/assets/use-sync-external-store-shim.production.js'
    ];
    
    for (const url of testUrls) {
      try {
        const response = await fetch(url);
        console.log(`📡 ${url}: ${response.status} ${response.statusText}`);
        
        if (url.includes('shim') && response.status === 200) {
          this.errors.push({
            type: 'shim_file_accessible',
            message: 'Shim file is accessible on server!',
            url: url,
            status: response.status
          });
          console.log('🚨 CRITICAL: Shim file found on server!');
        }
      } catch (error) {
        console.log(`❌ ${url}: ${error.message}`);
      }
    }
  }

  async simulatePageLoad() {
    console.log('\n📄 SIMULATING PAGE LOAD...');
    console.log('========================================');
    
    try {
      // Get the index.html content
      const response = await fetch('http://localhost:8080/');
      const html = await response.text();
      
      // Extract script tags
      const scriptMatches = html.match(/<script[^>]*src="([^"]*)"[^>]*>/g) || [];
      
      console.log(`📊 Found ${scriptMatches.length} script tags`);
      
      for (const scriptTag of scriptMatches) {
        const srcMatch = scriptTag.match(/src="([^"]*)"/);
        if (srcMatch) {
          const src = srcMatch[1];
          
          if (src.includes('sync-external-store') || src.includes('shim')) {
            this.errors.push({
              type: 'suspicious_script',
              message: 'Found suspicious script tag',
              src: src,
              tag: scriptTag
            });
            console.log(`🚨 SUSPICIOUS: ${src}`);
          } else {
            console.log(`✅ Script: ${src}`);
          }
        }
      }
      
      // Look for inline scripts that might load shim
      const inlineScripts = html.match(/<script[^>]*>(.*?)<\/script>/gs) || [];
      console.log(`📝 Found ${inlineScripts.length} inline scripts`);
      
      for (const script of inlineScripts) {
        if (script.includes('sync-external-store') || script.includes('shim')) {
          console.log('🚨 FOUND: Inline script mentions shim!');
          console.log(script.substring(0, 200) + '...');
        }
      }
      
    } catch (error) {
      console.error('❌ Error simulating page load:', error.message);
    }
  }

  generateReport() {
    console.log('\n📋 DEBUGGING REPORT');
    console.log('========================================');
    console.log(`🕐 Timestamp: ${new Date().toISOString()}`);
    console.log(`🚨 Errors found: ${this.errors.length}`);
    console.log(`📊 Total findings: ${this.findings.length}`);
    
    if (this.errors.length > 0) {
      console.log('\n🎯 CRITICAL FINDINGS:');
      this.errors.forEach((error, index) => {
        console.log(`\n--- Error ${index + 1} ---`);
        console.log(`Type: ${error.type}`);
        console.log(`Message: ${error.message}`);
        if (error.file) console.log(`File: ${error.file}`);
        if (error.line) console.log(`Line: ${error.line}`);
        if (error.url) console.log(`URL: ${error.url}`);
        if (error.content) console.log(`Content: ${error.content}`);
      });
      
      console.log('\n✅ SUCCESS: Found potential causes of the useState error!');
      console.log('🔧 These findings can help pinpoint why the error persists.');
      
      return true;
    } else {
      console.log('\n❓ No obvious issues found in build files');
      console.log('🤔 The error might be browser cache or environment specific');
      
      return false;
    }
  }
}

// Main execution
async function main() {
  const simpleDebugger = new SimpleDebugger();
  
  console.log('🔍 SIMPLE FILE-BASED DEBUGGING');
  console.log('==============================');
  console.log('This tool analyzes build files without requiring browser dependencies\n');
  
  await simpleDebugger.analyzeBuildFiles();
  await simpleDebugger.testServerResponse();
  await simpleDebugger.simulatePageLoad();
  
  const foundIssues = simpleDebugger.generateReport();
  
  process.exit(foundIssues ? 0 : 1);
}

main().catch(error => {
  console.error('💥 Simple debugger failed:', error);
  process.exit(2);
});