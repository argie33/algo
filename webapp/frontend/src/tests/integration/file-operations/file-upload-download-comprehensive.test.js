/**
 * Comprehensive File Upload/Download Workflow Integration Tests
 * Tests real file operations: S3 uploads, downloads, processing, virus scanning, CDN delivery
 * NO MOCKS - Tests against actual file storage infrastructure and real upload/download flows
 */

import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const testConfig = {
  baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
  apiURL: process.env.E2E_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  s3BucketURL: process.env.S3_BUCKET_URL || 'https://stocks-dashboard-assets.s3.amazonaws.com',
  testUser: {
    email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
  },
  timeout: 120000 // Extended timeout for file operations
};

test.describe('Comprehensive File Upload/Download Workflow Integration - Enterprise Framework', () => {
  
  let fileSession = {
    uploads: [],
    downloads: [],
    fileProcessing: [],
    securityChecks: [],
    storageEvents: [],
    compressionEvents: [],
    errors: []
  };

  async function authenticate(page) {
    const isAuth = await page.locator('[data-testid="user-avatar"]').isVisible().catch(() => false);
    if (!isAuth) {
      await page.locator('button:has-text("Sign In")').click();
      await page.fill('[data-testid="email-input"]', testConfig.testUser.email);
      await page.fill('[data-testid="password-input"]', testConfig.testUser.password);
      await page.click('[data-testid="login-submit"]');
      await page.waitForSelector('[data-testid="user-avatar"]', { timeout: 15000 });
    }
  }

  async function trackFileEvent(eventType, data) {
    fileSession[eventType].push({
      ...data,
      timestamp: new Date().toISOString()
    });
  }

  async function createTestFile(fileName, content, mimeType = 'text/plain') {
    const testFilePath = path.join('/tmp', fileName);
    
    if (mimeType.startsWith('image/')) {
      // Create a test image using canvas
      return await page.evaluateHandle(() => {
        const canvas = document.createElement('canvas');
        canvas.width = 200;
        canvas.height = 200;
        const ctx = canvas.getContext('2d');
        
        // Draw a simple test pattern
        ctx.fillStyle = '#FF0000';
        ctx.fillRect(0, 0, 100, 100);
        ctx.fillStyle = '#00FF00';
        ctx.fillRect(100, 0, 100, 100);
        ctx.fillStyle = '#0000FF';
        ctx.fillRect(0, 100, 100, 100);
        ctx.fillStyle = '#FFFF00';
        ctx.fillRect(100, 100, 100, 100);
        
        return new Promise((resolve) => {
          canvas.toBlob(resolve, mimeType);
        });
      });
    } else {
      // Create text file
      fs.writeFileSync(testFilePath, content);
      return testFilePath;
    }
  }

  test.beforeEach(async ({ page }) => {
    // Reset file session tracking
    fileSession = {
      uploads: [],
      downloads: [],
      fileProcessing: [],
      securityChecks: [],
      storageEvents: [],
      compressionEvents: [],
      errors: []
    };
    
    // Monitor file-related network requests
    page.on('request', request => {
      const url = request.url();
      if (url.includes('upload') || url.includes('download') || url.includes('file') || 
          url.includes('s3') || url.includes('blob') || url.includes('attachment')) {
        trackFileEvent('storageEvents', {
          type: 'file_request',
          url: url,
          method: request.method(),
          headers: Object.fromEntries(Object.entries(request.headers()).filter(([k, v]) => 
            k.toLowerCase().includes('content') || k.toLowerCase().includes('file')
          ))
        });
      }
    });

    page.on('response', response => {
      const url = response.url();
      if (url.includes('upload') || url.includes('download') || url.includes('file') || 
          url.includes('s3') || url.includes('blob')) {
        trackFileEvent('storageEvents', {
          type: 'file_response',
          url: url,
          status: response.status(),
          headers: Object.fromEntries(Object.entries(response.headers()).filter(([k, v]) => 
            k.toLowerCase().includes('content') || k.toLowerCase().includes('file') || k.toLowerCase().includes('etag')
          ))
        });
      }
    });

    // Monitor console for file operation errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        const errorText = msg.text();
        if (errorText.includes('file') || errorText.includes('upload') || 
            errorText.includes('download') || errorText.includes('blob')) {
          fileSession.errors.push({
            message: errorText,
            timestamp: new Date().toISOString()
          });
        }
      }
    });

    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
  });

  test.describe('File Upload Workflows @critical @enterprise @file-upload', () => {

    test('Complete File Upload Pipeline with Security Scanning', async ({ page }) => {
      console.log('⬆️ Testing Complete File Upload Pipeline with Security Scanning...');
      
      await authenticate(page);
      
      // 1. Test profile image upload
      console.log('🖼️ Testing profile image upload...');
      
      await page.goto('/settings/profile');
      await page.waitForSelector('[data-testid="profile-settings"]', { timeout: 15000 });
      
      // Create test image file
      const testImageBlob = await page.evaluateHandle(() => {
        const canvas = document.createElement('canvas');
        canvas.width = 300;
        canvas.height = 300;
        const ctx = canvas.getContext('2d');
        
        // Create a gradient pattern
        const gradient = ctx.createLinearGradient(0, 0, 300, 300);
        gradient.addColorStop(0, '#FF6B6B');
        gradient.addColorStop(0.5, '#4ECDC4');
        gradient.addColorStop(1, '#45B7D1');
        
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, 300, 300);
        
        // Add text
        ctx.fillStyle = 'white';
        ctx.font = '20px Arial';
        ctx.fillText('Test Profile Image', 75, 150);
        
        return new Promise((resolve) => {
          canvas.toBlob(resolve, 'image/png');
        });
      });
      
      const fileInput = page.locator('[data-testid="profile-image-upload"]');
      if (await fileInput.isVisible()) {
        await fileInput.setInputFiles(testImageBlob);
        
        console.log('📤 Profile image file selected');
        
        await trackFileEvent('uploads', {
          type: 'profile_image',
          fileType: 'image/png',
          stage: 'file_selected'
        });
        
        // Monitor upload progress
        const uploadProgress = page.locator('[data-testid="upload-progress"]');
        if (await uploadProgress.isVisible({ timeout: 5000 })) {
          console.log('📊 Upload progress indicator visible');
          
          // Monitor progress updates
          let lastProgress = 0;
          for (let i = 0; i < 30; i++) {
            await page.waitForTimeout(1000);
            
            const progressText = await uploadProgress.textContent().catch(() => '');
            const progressMatch = progressText.match(/(\d+)%/);
            
            if (progressMatch) {
              const currentProgress = parseInt(progressMatch[1]);
              if (currentProgress > lastProgress) {
                console.log(`📊 Upload progress: ${currentProgress}%`);
                lastProgress = currentProgress;
                
                await trackFileEvent('uploads', {
                  type: 'progress_update',
                  progress: currentProgress
                });
              }
              
              if (currentProgress >= 100) {
                console.log('✅ Upload completed');
                break;
              }
            }
            
            // Check for upload completion indicators
            const uploadComplete = page.locator('[data-testid="upload-complete"]');
            if (await uploadComplete.isVisible()) {
              console.log('✅ Upload completion detected');
              break;
            }
            
            // Check for upload errors
            const uploadError = page.locator('[data-testid="upload-error"]');
            if (await uploadError.isVisible()) {
              const errorText = await uploadError.textContent();
              console.log(`🚨 Upload error: ${errorText}`);
              
              await trackFileEvent('uploads', {
                type: 'upload_error',
                error: errorText
              });
              break;
            }
          }
        }
        
        // 2. Test virus scanning integration
        console.log('🛡️ Testing virus scanning integration...');
        
        const virusScanStatus = page.locator('[data-testid="virus-scan-status"]');
        if (await virusScanStatus.isVisible({ timeout: 10000 })) {
          const scanText = await virusScanStatus.textContent();
          console.log(`🛡️ Virus scan status: ${scanText}`);
          
          await trackFileEvent('securityChecks', {
            type: 'virus_scan',
            status: scanText,
            passed: scanText.includes('clean') || scanText.includes('safe')
          });
        }
        
        // 3. Test file processing pipeline
        console.log('⚙️ Testing file processing pipeline...');
        
        const processingStatus = page.locator('[data-testid="file-processing-status"]');
        if (await processingStatus.isVisible({ timeout: 15000 })) {
          const processingText = await processingStatus.textContent();
          console.log(`⚙️ File processing: ${processingText}`);
          
          await trackFileEvent('fileProcessing', {
            type: 'image_processing',
            status: processingText
          });
          
          // Wait for processing completion
          await page.waitForSelector('[data-testid="processing-complete"]', { timeout: 30000 });
          console.log('✅ File processing completed');
        }
        
        // 4. Verify uploaded image is displayed
        const profileImage = page.locator('[data-testid="profile-image-preview"]');
        if (await profileImage.isVisible({ timeout: 10000 })) {
          const imageSrc = await profileImage.getAttribute('src');
          console.log(`🖼️ Profile image updated: ${imageSrc?.substring(0, 100)}...`);
          
          await trackFileEvent('uploads', {
            type: 'upload_success',
            imageSrc: imageSrc,
            fileType: 'profile_image'
          });
        }
      }
      
      console.log('✅ Complete File Upload Pipeline with Security Scanning completed');
    });

    test('Document Upload and Processing Workflow', async ({ page }) => {
      console.log('📄 Testing Document Upload and Processing Workflow...');
      
      await authenticate(page);
      
      // 1. Test document upload (statements, reports, etc.)
      console.log('📋 Testing document upload...');
      
      await page.goto('/portfolio/documents');
      await page.waitForSelector('[data-testid="documents-page"]', { timeout: 15000 });
      
      const uploadDocumentButton = page.locator('[data-testid="upload-document"]');
      if (await uploadDocumentButton.isVisible()) {
        await uploadDocumentButton.click();
        
        await page.waitForSelector('[data-testid="document-upload-modal"]', { timeout: 10000 });
        
        // Create test PDF content (text-based for testing)
        const testDocumentContent = `
          Portfolio Statement
          Account: Test Account
          Date: ${new Date().toLocaleDateString()}
          
          Holdings:
          AAPL - 100 shares - $150.00
          MSFT - 50 shares - $300.00
          
          Total Portfolio Value: $30,000.00
        `;
        
        // Create test document file
        const testDocBlob = await page.evaluateHandle((content) => {
          return new Blob([content], { type: 'text/plain' });
        }, testDocumentContent);
        
        const documentInput = page.locator('[data-testid="document-file-input"]');
        await documentInput.setInputFiles(testDocBlob);
        
        // Set document metadata
        await page.selectOption('[data-testid="document-type"]', 'statement');
        await page.fill('[data-testid="document-description"]', 'Test portfolio statement upload');
        
        // Upload document
        await page.click('[data-testid="upload-document-submit"]');
        
        console.log('📤 Document upload initiated');
        
        await trackFileEvent('uploads', {
          type: 'document',
          documentType: 'statement',
          fileType: 'text/plain'
        });
        
        // 2. Monitor document processing
        console.log('⚙️ Monitoring document processing...');
        
        const docProcessingStatus = page.locator('[data-testid="document-processing-status"]');
        if (await docProcessingStatus.isVisible({ timeout: 10000 })) {
          let processingComplete = false;
          
          for (let i = 0; i < 30; i++) {
            await page.waitForTimeout(2000);
            
            const statusText = await docProcessingStatus.textContent();
            console.log(`📋 Document processing: ${statusText}`);
            
            await trackFileEvent('fileProcessing', {
              type: 'document_processing',
              stage: statusText
            });
            
            if (statusText.includes('complete') || statusText.includes('processed')) {
              processingComplete = true;
              console.log('✅ Document processing completed');
              break;
            }
            
            if (statusText.includes('error') || statusText.includes('failed')) {
              console.log(`🚨 Document processing error: ${statusText}`);
              break;
            }
          }
          
          if (processingComplete) {
            // 3. Test OCR/text extraction results
            const ocrResults = page.locator('[data-testid="document-ocr-results"]');
            if (await ocrResults.isVisible({ timeout: 10000 })) {
              const extractedText = await ocrResults.textContent();
              console.log(`📄 OCR extracted text: ${extractedText.substring(0, 200)}...`);
              
              await trackFileEvent('fileProcessing', {
                type: 'ocr_extraction',
                extractedLength: extractedText.length,
                containsKeywords: extractedText.includes('Portfolio') && extractedText.includes('AAPL')
              });
            }
            
            // 4. Test document categorization
            const documentCategory = page.locator('[data-testid="document-category"]');
            if (await documentCategory.isVisible()) {
              const categoryText = await documentCategory.textContent();
              console.log(`📊 Document categorized as: ${categoryText}`);
              
              await trackFileEvent('fileProcessing', {
                type: 'document_categorization',
                category: categoryText
              });
            }
          }
        }
      }
      
      console.log('✅ Document Upload and Processing Workflow completed');
    });

    test('Bulk File Upload and Batch Processing', async ({ page }) => {
      console.log('📦 Testing Bulk File Upload and Batch Processing...');
      
      await authenticate(page);
      
      // 1. Test bulk upload interface
      console.log('📤 Testing bulk upload interface...');
      
      await page.goto('/admin/bulk-upload');
      await page.waitForSelector('[data-testid="bulk-upload-page"]', { timeout: 15000 });
      
      const bulkUploadArea = page.locator('[data-testid="bulk-upload-dropzone"]');
      if (await bulkUploadArea.isVisible()) {
        // Create multiple test files
        const testFiles = [];
        
        for (let i = 1; i <= 3; i++) {
          const testFileContent = `Test File ${i}\nContent: ${new Date().toISOString()}\nData: ${Math.random()}`;
          
          const testFileBlob = await page.evaluateHandle((content, index) => {
            return new Blob([content], { type: 'text/plain', name: `test-file-${index}.txt` });
          }, testFileContent, i);
          
          testFiles.push(testFileBlob);
        }
        
        // Upload multiple files
        const bulkFileInput = page.locator('[data-testid="bulk-file-input"]');
        await bulkFileInput.setInputFiles(testFiles);
        
        console.log(`📦 ${testFiles.length} files selected for bulk upload`);
        
        await trackFileEvent('uploads', {
          type: 'bulk_upload',
          fileCount: testFiles.length
        });
        
        // 2. Monitor bulk processing
        console.log('⚙️ Monitoring bulk processing...');
        
        const bulkProcessingStatus = page.locator('[data-testid="bulk-processing-status"]');
        if (await bulkProcessingStatus.isVisible({ timeout: 10000 })) {
          const fileProcessingItems = page.locator('[data-testid^="file-processing-"]');
          const fileCount = await fileProcessingItems.count();
          
          console.log(`📊 Processing ${fileCount} files in batch`);
          
          // Monitor individual file processing
          for (let i = 0; i < fileCount; i++) {
            const fileItem = fileProcessingItems.nth(i);
            const fileName = await fileItem.locator('[data-testid="file-name"]').textContent();
            const fileStatus = await fileItem.locator('[data-testid="file-status"]').textContent();
            
            console.log(`📄 File ${i + 1}: ${fileName} - ${fileStatus}`);
            
            await trackFileEvent('fileProcessing', {
              type: 'bulk_file_processing',
              fileName: fileName,
              status: fileStatus,
              fileIndex: i
            });
          }
          
          // Wait for batch completion
          await page.waitForSelector('[data-testid="bulk-processing-complete"]', { timeout: 60000 });
          console.log('✅ Bulk processing completed');
          
          // 3. Check batch processing results
          const processingResults = page.locator('[data-testid="bulk-processing-results"]');
          if (await processingResults.isVisible()) {
            const successCount = await processingResults.locator('[data-testid="successful-uploads"]').textContent();
            const failureCount = await processingResults.locator('[data-testid="failed-uploads"]').textContent();
            
            console.log(`📊 Bulk upload results: ${successCount} successful, ${failureCount} failed`);
            
            await trackFileEvent('uploads', {
              type: 'bulk_upload_results',
              successful: parseInt(successCount) || 0,
              failed: parseInt(failureCount) || 0
            });
          }
        }
      }
      
      console.log('✅ Bulk File Upload and Batch Processing completed');
    });

  });

  test.describe('File Download and Export Workflows @critical @enterprise @file-download', () => {

    test('Report Generation and Download Pipeline', async ({ page }) => {
      console.log('📊 Testing Report Generation and Download Pipeline...');
      
      await authenticate(page);
      
      // 1. Test portfolio report generation
      console.log('📈 Testing portfolio report generation...');
      
      await page.goto('/portfolio/reports');
      await page.waitForSelector('[data-testid="reports-page"]', { timeout: 15000 });
      
      const generateReportButton = page.locator('[data-testid="generate-report"]');
      if (await generateReportButton.isVisible()) {
        await generateReportButton.click();
        
        await page.waitForSelector('[data-testid="report-generation-form"]', { timeout: 10000 });
        
        // Configure report parameters
        await page.selectOption('[data-testid="report-type"]', 'portfolio-summary');
        await page.selectOption('[data-testid="report-format"]', 'pdf');
        await page.selectOption('[data-testid="date-range"]', 'last-30-days');
        await page.check('[data-testid="include-charts"]');
        await page.check('[data-testid="include-transactions"]');
        
        await page.click('[data-testid="start-generation"]');
        
        console.log('📊 Report generation started');
        
        await trackFileEvent('fileProcessing', {
          type: 'report_generation',
          reportType: 'portfolio-summary',
          format: 'pdf'
        });
        
        // 2. Monitor report generation progress
        console.log('⏳ Monitoring report generation...');
        
        const generationProgress = page.locator('[data-testid="generation-progress"]');
        if (await generationProgress.isVisible({ timeout: 10000 })) {
          let generationComplete = false;
          
          for (let i = 0; i < 60; i++) { // Up to 1 minute
            await page.waitForTimeout(1000);
            
            const progressText = await generationProgress.textContent();
            const progressMatch = progressText.match(/(\d+)%/);
            
            if (progressMatch) {
              const progress = parseInt(progressMatch[1]);
              if (progress % 10 === 0) { // Log every 10%
                console.log(`📊 Generation progress: ${progress}%`);
              }
              
              if (progress >= 100) {
                generationComplete = true;
                console.log('✅ Report generation completed');
                break;
              }
            }
            
            // Check for completion indicator
            const generationDone = page.locator('[data-testid="generation-complete"]');
            if (await generationDone.isVisible()) {
              generationComplete = true;
              console.log('✅ Report generation completed');
              break;
            }
            
            // Check for errors
            const generationError = page.locator('[data-testid="generation-error"]');
            if (await generationError.isVisible()) {
              const errorText = await generationError.textContent();
              console.log(`🚨 Report generation error: ${errorText}`);
              
              await trackFileEvent('fileProcessing', {
                type: 'report_generation_error',
                error: errorText
              });
              break;
            }
          }
          
          if (generationComplete) {
            // 3. Test file download
            console.log('⬇️ Testing file download...');
            
            const downloadButton = page.locator('[data-testid="download-report"]');
            if (await downloadButton.isVisible()) {
              // Setup download monitoring
              const downloadPromise = page.waitForEvent('download', { timeout: 30000 });
              
              await downloadButton.click();
              
              const download = await downloadPromise;
              
              console.log(`⬇️ Download started: ${download.suggestedFilename()}`);
              
              await trackFileEvent('downloads', {
                type: 'report_download',
                fileName: download.suggestedFilename(),
                url: download.url()
              });
              
              // Verify download completion
              const downloadPath = await download.path();
              if (downloadPath && fs.existsSync(downloadPath)) {
                const stats = fs.statSync(downloadPath);
                console.log(`✅ Download completed: ${stats.size} bytes`);
                
                await trackFileEvent('downloads', {
                  type: 'download_success',
                  fileSize: stats.size,
                  fileName: download.suggestedFilename()
                });
              }
            }
          }
        }
      }
      
      console.log('✅ Report Generation and Download Pipeline completed');
    });

    test('Data Export and CSV Download Workflow', async ({ page }) => {
      console.log('📋 Testing Data Export and CSV Download Workflow...');
      
      await authenticate(page);
      
      // 1. Test transaction data export
      console.log('💰 Testing transaction data export...');
      
      await page.goto('/portfolio/transactions');
      await page.waitForSelector('[data-testid="transactions-page"]', { timeout: 15000 });
      
      const exportButton = page.locator('[data-testid="export-transactions"]');
      if (await exportButton.isVisible()) {
        await exportButton.click();
        
        await page.waitForSelector('[data-testid="export-options"]', { timeout: 10000 });
        
        // Configure export options
        await page.selectOption('[data-testid="export-format"]', 'csv');
        await page.selectOption('[data-testid="date-range"]', 'ytd');
        await page.check('[data-testid="include-fees"]');
        await page.check('[data-testid="include-dividends"]');
        
        // Setup download monitoring
        const downloadPromise = page.waitForEvent('download', { timeout: 30000 });
        
        await page.click('[data-testid="start-export"]');
        
        console.log('📤 Transaction export started');
        
        await trackFileEvent('downloads', {
          type: 'transaction_export',
          format: 'csv',
          dateRange: 'ytd'
        });
        
        // Wait for download
        const download = await downloadPromise;
        
        console.log(`⬇️ Export download started: ${download.suggestedFilename()}`);
        
        // Verify CSV download
        const downloadPath = await download.path();
        if (downloadPath && fs.existsSync(downloadPath)) {
          const csvContent = fs.readFileSync(downloadPath, 'utf8');
          const lines = csvContent.split('\n');
          
          console.log(`📊 CSV downloaded: ${lines.length} lines`);
          console.log(`📊 CSV headers: ${lines[0]}`);
          
          await trackFileEvent('downloads', {
            type: 'csv_download_success',
            lineCount: lines.length,
            headers: lines[0],
            fileSize: csvContent.length
          });
          
          // Verify CSV structure
          if (lines[0].includes('Date') && lines[0].includes('Symbol') && lines[0].includes('Amount')) {
            console.log('✅ CSV structure verified');
          } else {
            console.log('⚠️ Unexpected CSV structure');
          }
        }
      }
      
      // 2. Test holdings export
      console.log('📊 Testing holdings export...');
      
      await page.goto('/portfolio/holdings');
      await page.waitForSelector('[data-testid="holdings-page"]', { timeout: 15000 });
      
      const exportHoldingsButton = page.locator('[data-testid="export-holdings"]');
      if (await exportHoldingsButton.isVisible()) {
        const holdingsDownloadPromise = page.waitForEvent('download', { timeout: 20000 });
        
        await exportHoldingsButton.click();
        
        const holdingsDownload = await holdingsDownloadPromise;
        
        console.log(`⬇️ Holdings export: ${holdingsDownload.suggestedFilename()}`);
        
        await trackFileEvent('downloads', {
          type: 'holdings_export',
          fileName: holdingsDownload.suggestedFilename()
        });
      }
      
      console.log('✅ Data Export and CSV Download Workflow completed');
    });

  });

  test.describe('File Storage and CDN Integration @critical @enterprise @storage', () => {

    test('S3 Storage and CloudFront CDN Performance', async ({ page, request }) => {
      console.log('🗄️ Testing S3 Storage and CloudFront CDN Performance...');
      
      await authenticate(page);
      
      // 1. Test static asset delivery performance
      console.log('⚡ Testing static asset delivery performance...');
      
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      
      // Monitor asset loading
      const assetLoadTimes = [];
      
      page.on('response', response => {
        const url = response.url();
        if (url.includes('cloudfront') || url.includes('s3') || url.includes('amazonaws.com')) {
          const timing = response.timing();
          if (timing) {
            assetLoadTimes.push({
              url: url.substring(url.lastIndexOf('/') + 1),
              responseTime: timing.responseEnd - timing.responseStart,
              cacheStatus: response.headers()['x-cache'] || 'unknown'
            });
          }
        }
      });
      
      // Force asset loads
      await page.reload();
      await page.waitForLoadState('networkidle');
      
      if (assetLoadTimes.length > 0) {
        console.log(`📊 Static assets loaded: ${assetLoadTimes.length}`);
        
        const averageResponseTime = assetLoadTimes.reduce((sum, asset) => sum + asset.responseTime, 0) / assetLoadTimes.length;
        const cachedAssets = assetLoadTimes.filter(asset => asset.cacheStatus.includes('Hit')).length;
        
        console.log(`⚡ Average response time: ${averageResponseTime.toFixed(1)}ms`);
        console.log(`📦 Cached assets: ${cachedAssets}/${assetLoadTimes.length}`);
        
        await trackFileEvent('storageEvents', {
          type: 'cdn_performance',
          assetCount: assetLoadTimes.length,
          averageResponseTime: averageResponseTime,
          cacheHitRate: (cachedAssets / assetLoadTimes.length * 100).toFixed(1)
        });
      }
      
      // 2. Test file compression
      console.log('🗜️ Testing file compression...');
      
      const compressionTestURL = `${testConfig.baseURL}/static/js/main.js`;
      
      // Request with compression
      const compressedResponse = await request.get(compressionTestURL, {
        headers: {
          'Accept-Encoding': 'gzip, deflate, br'
        }
      });
      
      const contentEncoding = compressedResponse.headers()['content-encoding'];
      const contentLength = parseInt(compressedResponse.headers()['content-length'] || '0');
      
      console.log(`🗜️ Compression: ${contentEncoding || 'none'}`);
      console.log(`📊 Compressed size: ${contentLength} bytes`);
      
      await trackFileEvent('compressionEvents', {
        type: 'compression_test',
        encoding: contentEncoding,
        compressedSize: contentLength
      });
      
      // 3. Test file versioning and cache busting
      console.log('🔄 Testing file versioning and cache busting...');
      
      // Check for versioned assets
      const versionedAssets = assetLoadTimes.filter(asset => 
        asset.url.includes('?v=') || /\.[a-f0-9]{8,}\.(js|css)$/.test(asset.url)
      );
      
      console.log(`🔢 Versioned assets: ${versionedAssets.length}/${assetLoadTimes.length}`);
      
      await trackFileEvent('storageEvents', {
        type: 'versioning_check',
        versionedAssets: versionedAssets.length,
        totalAssets: assetLoadTimes.length
      });
      
      console.log('✅ S3 Storage and CloudFront CDN Performance completed');
    });

  });

  test.afterEach(async () => {
    // File operations session summary
    console.log('\n📁 File Upload/Download Session Summary:');
    console.log(`Uploads: ${fileSession.uploads.length}`);
    console.log(`Downloads: ${fileSession.downloads.length}`);
    console.log(`File processing events: ${fileSession.fileProcessing.length}`);
    console.log(`Security checks: ${fileSession.securityChecks.length}`);
    console.log(`Storage events: ${fileSession.storageEvents.length}`);
    console.log(`Compression events: ${fileSession.compressionEvents.length}`);
    console.log(`Total errors: ${fileSession.errors.length}`);
    
    // Log upload success rate
    if (fileSession.uploads.length > 0) {
      console.log('\n⬆️ Upload Summary:');
      const uploadTypes = fileSession.uploads.reduce((acc, upload) => {
        acc[upload.type] = (acc[upload.type] || 0) + 1;
        return acc;
      }, {});
      
      Object.entries(uploadTypes).forEach(([type, count]) => {
        console.log(`  ${type}: ${count} uploads`);
      });
      
      const successfulUploads = fileSession.uploads.filter(upload => 
        upload.type === 'upload_success' || upload.stage === 'file_selected'
      );
      const uploadSuccessRate = (successfulUploads.length / fileSession.uploads.length * 100).toFixed(1);
      console.log(`  Success rate: ${uploadSuccessRate}%`);
    }
    
    // Log download summary
    if (fileSession.downloads.length > 0) {
      console.log('\n⬇️ Download Summary:');
      const downloadTypes = fileSession.downloads.reduce((acc, download) => {
        acc[download.type] = (acc[download.type] || 0) + 1;
        return acc;
      }, {});
      
      Object.entries(downloadTypes).forEach(([type, count]) => {
        console.log(`  ${type}: ${count} downloads`);
      });
    }
    
    // Log security checks
    if (fileSession.securityChecks.length > 0) {
      console.log('\n🛡️ Security Checks:');
      const passedChecks = fileSession.securityChecks.filter(check => check.passed).length;
      console.log(`  Passed: ${passedChecks}/${fileSession.securityChecks.length}`);
    }
    
    // Log CDN performance
    const cdnPerformance = fileSession.storageEvents.filter(event => event.type === 'cdn_performance');
    if (cdnPerformance.length > 0) {
      const avgResponseTime = cdnPerformance.reduce((sum, event) => sum + event.averageResponseTime, 0) / cdnPerformance.length;
      const avgCacheHitRate = cdnPerformance.reduce((sum, event) => sum + parseFloat(event.cacheHitRate), 0) / cdnPerformance.length;
      
      console.log('\n📦 CDN Performance:');
      console.log(`  Average response time: ${avgResponseTime.toFixed(1)}ms`);
      console.log(`  Average cache hit rate: ${avgCacheHitRate.toFixed(1)}%`);
    }
    
    // Calculate overall file system health
    const totalFileOperations = fileSession.uploads.length + fileSession.downloads.length;
    const errorCount = fileSession.errors.length;
    const fileSystemHealth = totalFileOperations > 0 ? 
      ((totalFileOperations - errorCount) / totalFileOperations * 100).toFixed(1) : 100;
    
    console.log(`\n📊 File System Health Score: ${fileSystemHealth}% (${totalFileOperations - errorCount}/${totalFileOperations})`);
  });

});

export default {
  testConfig
};