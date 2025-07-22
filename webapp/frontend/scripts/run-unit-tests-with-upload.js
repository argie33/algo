#!/usr/bin/env node

/**
 * Unit Test Runner with S3 Upload - NO MOCKS
 * Runs unit tests and uploads results to S3 like integration tests
 */

import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const TEST_CONFIG = {
  timestamp: new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5),
  runId: Date.now().toString(),
  branch: process.env.GITHUB_REF_NAME || process.env.BRANCH_NAME || 'local',
  commit: process.env.GITHUB_SHA || 'local-commit',
  resultsDir: './test-results',
  artifactsDir: './unit-test-artifacts'
};

async function ensureDirectories() {
  console.log('📁 Creating test result directories...');
  
  [TEST_CONFIG.resultsDir, TEST_CONFIG.artifactsDir].forEach(dir => {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
      console.log(`✅ Created directory: ${dir}`);
    }
  });
}

async function runUnitTests() {
  console.log('🧪 Running unit tests...');
  
  try {
    const testCommand = 'npm run test:unit -- --reporter=json --outputFile=./test-results/unit-results.json';
    console.log(`Executing: ${testCommand}`);
    
    const output = execSync(testCommand, { 
      encoding: 'utf8',
      stdio: 'pipe'
    });
    
    console.log('✅ Unit tests completed successfully');
    return { success: true, output };
  } catch (error) {
    console.error('❌ Unit tests failed:', error.message);
    
    // Still create results file even on failure
    const failureResult = {
      timestamp: TEST_CONFIG.timestamp,
      success: false,
      error: error.message,
      exitCode: error.status || 1
    };
    
    fs.writeFileSync('./test-results/unit-results.json', JSON.stringify(failureResult, null, 2));
    return { success: false, output: error.stdout || error.message };
  }
}

async function generateTestSummary() {
  console.log('📊 Generating test summary...');
  
  const summaryData = {
    timestamp: TEST_CONFIG.timestamp,
    runId: TEST_CONFIG.runId,
    branch: TEST_CONFIG.branch,
    commit: TEST_CONFIG.commit,
    testType: 'unit',
    environment: 'ci'
  };
  
  // Try to read test results
  try {
    if (fs.existsSync('./test-results/unit-results.json')) {
      const testResults = JSON.parse(fs.readFileSync('./test-results/unit-results.json', 'utf8'));
      summaryData.testResults = testResults;
      summaryData.success = testResults.success !== false;
    } else {
      summaryData.success = false;
      summaryData.error = 'No test results file found';
    }
  } catch (error) {
    summaryData.success = false;
    summaryData.error = `Failed to read test results: ${error.message}`;
  }
  
  // Write summary
  const summaryPath = path.join(TEST_CONFIG.artifactsDir, 'test-summary.json');
  fs.writeFileSync(summaryPath, JSON.stringify(summaryData, null, 2));
  console.log(`✅ Test summary written to ${summaryPath}`);
  
  return summaryData;
}

async function collectCoverage() {
  console.log('📈 Collecting coverage data...');
  
  try {
    if (fs.existsSync('./coverage')) {
      const coverageFiles = fs.readdirSync('./coverage');
      console.log(`Found coverage files: ${coverageFiles.join(', ')}`);
      
      // Copy coverage to artifacts
      execSync(`cp -r ./coverage/* ${TEST_CONFIG.artifactsDir}/`, { stdio: 'inherit' });
      console.log('✅ Coverage data collected');
      return true;
    } else {
      console.log('⚠️ No coverage directory found');
      return false;
    }
  } catch (error) {
    console.error('❌ Failed to collect coverage:', error.message);
    return false;
  }
}

async function prepareS3Upload() {
  console.log('📦 Preparing S3 upload...');
  
  const uploadManifest = {
    timestamp: TEST_CONFIG.timestamp,
    runId: TEST_CONFIG.runId,
    branch: TEST_CONFIG.branch,
    commit: TEST_CONFIG.commit,
    testType: 'unit',
    files: []
  };
  
  // List all files in artifacts directory
  if (fs.existsSync(TEST_CONFIG.artifactsDir)) {
    const files = fs.readdirSync(TEST_CONFIG.artifactsDir, { recursive: true });
    uploadManifest.files = files.map(file => ({
      name: file,
      path: path.join(TEST_CONFIG.artifactsDir, file),
      size: fs.statSync(path.join(TEST_CONFIG.artifactsDir, file)).size
    }));
  }
  
  // Add test results
  if (fs.existsSync('./test-results/unit-results.json')) {
    uploadManifest.files.push({
      name: 'unit-results.json',
      path: './test-results/unit-results.json',
      size: fs.statSync('./test-results/unit-results.json').size
    });
  }
  
  // Write upload manifest
  const manifestPath = path.join(TEST_CONFIG.artifactsDir, 'upload-manifest.json');
  fs.writeFileSync(manifestPath, JSON.stringify(uploadManifest, null, 2));
  console.log(`✅ Upload manifest created: ${uploadManifest.files.length} files ready`);
  
  return uploadManifest;
}

async function uploadToS3() {
  console.log('☁️ Uploading to S3...');
  
  const s3Bucket = process.env.S3_TEST_RESULTS_BUCKET || 'stocks-dashboard-test-results';
  const s3KeyPrefix = `unit-tests/${TEST_CONFIG.branch}/${TEST_CONFIG.timestamp}`;
  
  try {
    // Upload artifacts directory
    const uploadCommand = `aws s3 sync ${TEST_CONFIG.artifactsDir} s3://${s3Bucket}/${s3KeyPrefix}/ --no-progress`;
    console.log(`Executing: ${uploadCommand}`);
    
    execSync(uploadCommand, { stdio: 'inherit' });
    console.log('✅ Artifacts uploaded to S3');
    
    // Upload test results
    if (fs.existsSync('./test-results/unit-results.json')) {
      const resultsUploadCommand = `aws s3 cp ./test-results/unit-results.json s3://${s3Bucket}/${s3KeyPrefix}/unit-results.json`;
      execSync(resultsUploadCommand, { stdio: 'inherit' });
      console.log('✅ Test results uploaded to S3');
    }
    
    console.log(`🔗 S3 Location: s3://${s3Bucket}/${s3KeyPrefix}/`);
    return true;
  } catch (error) {
    console.error('❌ S3 upload failed:', error.message);
    return false;
  }
}

async function main() {
  console.log('🚀 Starting Unit Test Runner with S3 Upload');
  console.log(`📊 Run ID: ${TEST_CONFIG.runId}`);
  console.log(`🌿 Branch: ${TEST_CONFIG.branch}`);
  console.log(`⏰ Timestamp: ${TEST_CONFIG.timestamp}`);
  
  try {
    // Step 1: Setup
    await ensureDirectories();
    
    // Step 2: Run tests
    const testResult = await runUnitTests();
    
    // Step 3: Collect coverage
    await collectCoverage();
    
    // Step 4: Generate summary
    const summary = await generateTestSummary();
    
    // Step 5: Prepare for upload
    const uploadManifest = await prepareS3Upload();
    
    // Step 6: Upload to S3 (only in CI environment)
    if (process.env.CI || process.env.GITHUB_ACTIONS) {
      const uploadSuccess = await uploadToS3();
      if (uploadSuccess) {
        console.log('🎉 Unit test results successfully uploaded to S3');
      } else {
        console.log('⚠️ S3 upload failed, but tests completed');
      }
    } else {
      console.log('ℹ️ Skipping S3 upload (not in CI environment)');
      console.log(`📁 Results available locally in: ${TEST_CONFIG.artifactsDir}`);
    }
    
    // Step 7: Final summary
    console.log('\\n📋 Final Summary:');
    console.log(`✅ Tests completed: ${summary.success ? 'SUCCESS' : 'FAILED'}`);
    console.log(`📊 Files prepared: ${uploadManifest.files.length}`);
    console.log(`📁 Artifacts directory: ${TEST_CONFIG.artifactsDir}`);
    
    process.exit(summary.success ? 0 : 1);
    
  } catch (error) {
    console.error('💥 Fatal error:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(error => {
  console.error('💥 Unhandled error:', error);
  process.exit(1);
});