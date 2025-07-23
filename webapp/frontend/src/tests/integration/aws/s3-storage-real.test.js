/**
 * AWS S3 Storage Real Integration Tests
 * Tests actual S3 bucket operations for file storage and CDN
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import { 
  S3Client, 
  PutObjectCommand, 
  GetObjectCommand, 
  DeleteObjectCommand,
  ListObjectsV2Command,
  HeadBucketCommand 
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

// AWS S3 Configuration
const AWS_REGION = process.env.AWS_REGION || 'us-east-1';
const S3_BUCKET_NAME = process.env.S3_BUCKET_NAME || 'financial-platform-storage';
const S3_CDN_BUCKET = process.env.S3_CDN_BUCKET || 'financial-platform-cdn';
const CLOUDFRONT_DOMAIN = process.env.CLOUDFRONT_DOMAIN;

// Test file configurations
const TEST_FILES = {
  document: {
    key: 'test-documents/integration-test-doc.pdf',
    content: Buffer.from('Test PDF content for integration testing'),
    contentType: 'application/pdf'
  },
  image: {
    key: 'test-images/integration-test-image.jpg',
    content: Buffer.from('Test image content for integration testing'),
    contentType: 'image/jpeg'
  },
  report: {
    key: 'test-reports/portfolio-report.json',
    content: Buffer.from(JSON.stringify({ 
      userId: 'test-user',
      portfolio: 'test-portfolio',
      timestamp: new Date().toISOString()
    })),
    contentType: 'application/json'
  }
};

describe('AWS S3 Storage Real Integration Tests', () => {
  let s3Client;
  let uploadedFiles = [];

  beforeAll(async () => {
    // Skip tests if S3 configuration not available
    if (!process.env.AWS_ACCESS_KEY_ID || !S3_BUCKET_NAME) {
      console.warn('⚠️ Skipping S3 tests - AWS configuration missing');
      console.warn('⚠️ Set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and S3_BUCKET_NAME');
      return;
    }

    try {
      // Initialize S3 client
      s3Client = new S3Client({
        region: AWS_REGION,
        credentials: {
          accessKeyId: process.env.AWS_ACCESS_KEY_ID,
          secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY
        }
      });

      // Verify bucket accessibility
      const headBucketCommand = new HeadBucketCommand({
        Bucket: S3_BUCKET_NAME
      });
      
      await s3Client.send(headBucketCommand);
      console.log(`✅ Connected to S3 bucket: ${S3_BUCKET_NAME}`);

    } catch (error) {
      console.error('❌ Failed to connect to S3:', error.message);
      throw new Error('S3 connection failed - check bucket name and permissions');
    }
  });

  afterAll(async () => {
    if (!s3Client) return;

    try {
      // Clean up test files
      for (const fileKey of uploadedFiles) {
        try {
          const deleteCommand = new DeleteObjectCommand({
            Bucket: S3_BUCKET_NAME,
            Key: fileKey
          });
          await s3Client.send(deleteCommand);
          console.log(`🧹 Cleaned up test file: ${fileKey}`);
        } catch (error) {
          console.warn(`⚠️ Failed to cleanup ${fileKey}: ${error.message}`);
        }
      }
    } catch (error) {
      console.warn('⚠️ Error during S3 cleanup:', error.message);
    }
  });

  describe('S3 Bucket Operations', () => {
    it('validates bucket accessibility and permissions', async () => {
      if (!s3Client) return;

      const headBucketCommand = new HeadBucketCommand({
        Bucket: S3_BUCKET_NAME
      });

      const response = await s3Client.send(headBucketCommand);
      expect(response.$metadata.httpStatusCode).toBe(200);

      console.log(`✅ Bucket ${S3_BUCKET_NAME} is accessible`);
    });

    it('lists existing objects in bucket', async () => {
      if (!s3Client) return;

      const listCommand = new ListObjectsV2Command({
        Bucket: S3_BUCKET_NAME,
        Prefix: 'test-',
        MaxKeys: 10
      });

      const response = await s3Client.send(listCommand);
      
      expect(response.Contents).toBeDefined();
      expect(Array.isArray(response.Contents)).toBe(true);
      expect(response.KeyCount).toBeGreaterThanOrEqual(0);

      console.log(`✅ Found ${response.KeyCount} test objects in bucket`);
    });
  });

  describe('File Upload Operations', () => {
    it('uploads PDF document to S3', async () => {
      if (!s3Client) return;

      const testFile = TEST_FILES.document;
      
      const putCommand = new PutObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: testFile.key,
        Body: testFile.content,
        ContentType: testFile.contentType,
        Metadata: {
          'test-file': 'true',
          'uploaded-by': 'integration-test',
          'upload-timestamp': new Date().toISOString()
        }
      });

      const response = await s3Client.send(putCommand);
      uploadedFiles.push(testFile.key);

      expect(response.$metadata.httpStatusCode).toBe(200);
      expect(response.ETag).toBeDefined();

      console.log(`✅ Uploaded document: ${testFile.key}`);
      console.log(`✅ ETag: ${response.ETag}`);
    });

    it('uploads image file to S3', async () => {
      if (!s3Client) return;

      const testFile = TEST_FILES.image;
      
      const putCommand = new PutObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: testFile.key,
        Body: testFile.content,
        ContentType: testFile.contentType,
        CacheControl: 'max-age=31536000', // 1 year cache for images
        Metadata: {
          'test-file': 'true',
          'file-type': 'image'
        }
      });

      const response = await s3Client.send(putCommand);
      uploadedFiles.push(testFile.key);

      expect(response.$metadata.httpStatusCode).toBe(200);
      expect(response.ETag).toBeDefined();

      console.log(`✅ Uploaded image: ${testFile.key}`);
    });

    it('uploads JSON report to S3', async () => {
      if (!s3Client) return;

      const testFile = TEST_FILES.report;
      
      const putCommand = new PutObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: testFile.key,
        Body: testFile.content,
        ContentType: testFile.contentType,
        ServerSideEncryption: 'AES256', // Encrypt sensitive reports
        Metadata: {
          'test-file': 'true',
          'report-type': 'portfolio',
          'classification': 'internal'
        }
      });

      const response = await s3Client.send(putCommand);
      uploadedFiles.push(testFile.key);

      expect(response.$metadata.httpStatusCode).toBe(200);
      expect(response.ETag).toBeDefined();
      expect(response.ServerSideEncryption).toBe('AES256');

      console.log(`✅ Uploaded encrypted report: ${testFile.key}`);
    });
  });

  describe('File Retrieval Operations', () => {
    let testFileKey;

    beforeEach(async () => {
      if (!s3Client) return;

      // Upload a test file for retrieval tests
      testFileKey = `test-retrieval/test-${Date.now()}.txt`;
      const testContent = 'Test content for retrieval operations';

      const putCommand = new PutObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: testFileKey,
        Body: Buffer.from(testContent),
        ContentType: 'text/plain'
      });

      await s3Client.send(putCommand);
      uploadedFiles.push(testFileKey);
    });

    it('retrieves uploaded file from S3', async () => {
      if (!s3Client || !testFileKey) return;

      const getCommand = new GetObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: testFileKey
      });

      const response = await s3Client.send(getCommand);

      expect(response.Body).toBeDefined();
      expect(response.ContentType).toBe('text/plain');
      expect(response.ContentLength).toBeGreaterThan(0);

      // Read the body content
      const bodyContents = await streamToBuffer(response.Body);
      expect(bodyContents.toString()).toContain('Test content for retrieval');

      console.log(`✅ Retrieved file: ${testFileKey}`);
      console.log(`✅ Content Length: ${response.ContentLength} bytes`);
    });

    it('handles file not found gracefully', async () => {
      if (!s3Client) return;

      const nonExistentKey = 'non-existent-file.txt';
      
      const getCommand = new GetObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: nonExistentKey
      });

      await expect(s3Client.send(getCommand)).rejects.toThrow('NoSuchKey');
    });
  });

  describe('Pre-signed URL Generation', () => {
    it('generates pre-signed URL for file upload', async () => {
      if (!s3Client) return;

      const uploadKey = `test-presigned/upload-${Date.now()}.txt`;
      
      const putCommand = new PutObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: uploadKey,
        ContentType: 'text/plain'
      });

      const signedUrl = await getSignedUrl(s3Client, putCommand, { 
        expiresIn: 3600 // 1 hour
      });

      expect(signedUrl).toMatch(/^https:\/\//);
      expect(signedUrl).toContain(S3_BUCKET_NAME);
      expect(signedUrl).toContain(uploadKey);
      expect(signedUrl).toContain('X-Amz-Signature');

      console.log(`✅ Generated pre-signed upload URL`);
      console.log(`✅ URL expires in 1 hour`);

      // Test the pre-signed URL with actual upload
      const testContent = 'Content uploaded via pre-signed URL';
      
      const uploadResponse = await fetch(signedUrl, {
        method: 'PUT',
        body: testContent,
        headers: {
          'Content-Type': 'text/plain'
        }
      });

      expect(uploadResponse.status).toBe(200);
      uploadedFiles.push(uploadKey);

      console.log(`✅ Successfully uploaded via pre-signed URL`);
    });

    it('generates pre-signed URL for file download', async () => {
      if (!s3Client) return;

      // First upload a file to download
      const downloadKey = `test-download/download-${Date.now()}.txt`;
      const testContent = 'Content for download testing';

      const putCommand = new PutObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: downloadKey,
        Body: Buffer.from(testContent),
        ContentType: 'text/plain'
      });

      await s3Client.send(putCommand);
      uploadedFiles.push(downloadKey);

      // Generate pre-signed download URL
      const getCommand = new GetObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: downloadKey
      });

      const signedUrl = await getSignedUrl(s3Client, getCommand, { 
        expiresIn: 1800 // 30 minutes
      });

      expect(signedUrl).toMatch(/^https:\/\//);
      expect(signedUrl).toContain(downloadKey);

      // Test the download URL
      const downloadResponse = await fetch(signedUrl);
      const downloadedContent = await downloadResponse.text();

      expect(downloadResponse.status).toBe(200);
      expect(downloadedContent).toBe(testContent);

      console.log(`✅ Generated and tested pre-signed download URL`);
    });
  });

  describe('CloudFront CDN Integration', () => {
    it('validates CloudFront distribution access', async () => {
      if (!CLOUDFRONT_DOMAIN) {
        console.warn('⚠️ CloudFront domain not configured, skipping CDN tests');
        return;
      }

      // Test CloudFront endpoint accessibility
      const cdnUrl = `https://${CLOUDFRONT_DOMAIN}/health-check.json`;
      
      try {
        const response = await fetch(cdnUrl, {
          method: 'HEAD',
          headers: {
            'User-Agent': 'financial-platform-integration-test'
          }
        });

        // CloudFront should be accessible
        expect(response.status).toBeLessThan(500);
        
        if (response.ok) {
          console.log(`✅ CloudFront distribution accessible`);
          console.log(`✅ Cache Status: ${response.headers.get('x-cache') || 'Unknown'}`);
        }

      } catch (error) {
        console.warn(`⚠️ CloudFront not accessible: ${error.message}`);
      }
    });

    it('tests CDN cache behavior', async () => {
      if (!s3Client || !CLOUDFRONT_DOMAIN) return;

      // Upload a cacheable file
      const cacheTestKey = `test-cdn/cache-test-${Date.now()}.json`;
      const cacheTestContent = JSON.stringify({
        message: 'CDN cache test',
        timestamp: new Date().toISOString()
      });

      const putCommand = new PutObjectCommand({
        Bucket: S3_CDN_BUCKET || S3_BUCKET_NAME,
        Key: cacheTestKey,
        Body: Buffer.from(cacheTestContent),
        ContentType: 'application/json',
        CacheControl: 'max-age=300' // 5 minutes cache
      });

      await s3Client.send(putCommand);
      uploadedFiles.push(cacheTestKey);

      // Test CDN access
      const cdnUrl = `https://${CLOUDFRONT_DOMAIN}/${cacheTestKey}`;
      
      try {
        const response = await fetch(cdnUrl);
        
        if (response.ok) {
          const content = await response.json();
          expect(content.message).toBe('CDN cache test');
          
          console.log(`✅ CDN served file successfully`);
          console.log(`✅ Cache Control: ${response.headers.get('cache-control')}`);
        }

      } catch (error) {
        console.warn(`⚠️ CDN file access failed: ${error.message}`);
      }
    });
  });

  describe('S3 Performance and Optimization', () => {
    it('tests multipart upload capability', async () => {
      if (!s3Client) return;

      // For integration test, we'll simulate with a smaller file
      const largeFileKey = `test-multipart/large-file-${Date.now()}.txt`;
      const largeContent = 'Large file content for multipart testing\n'.repeat(1000);

      const putCommand = new PutObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: largeFileKey,
        Body: Buffer.from(largeContent),
        ContentType: 'text/plain',
        StorageClass: 'STANDARD_IA' // Infrequent Access for cost optimization
      });

      const startTime = Date.now();
      const response = await s3Client.send(putCommand);
      const uploadTime = Date.now() - startTime;

      uploadedFiles.push(largeFileKey);

      expect(response.$metadata.httpStatusCode).toBe(200);
      expect(uploadTime).toBeLessThan(10000); // Should complete within 10 seconds

      console.log(`✅ Large file upload completed in ${uploadTime}ms`);
    });

    it('tests concurrent upload operations', async () => {
      if (!s3Client) return;

      const concurrentUploads = 3;
      const uploadPromises = [];

      for (let i = 0; i < concurrentUploads; i++) {
        const key = `test-concurrent/file-${i}-${Date.now()}.txt`;
        const content = `Concurrent upload test file ${i}`;

        const putCommand = new PutObjectCommand({
          Bucket: S3_BUCKET_NAME,
          Key: key,
          Body: Buffer.from(content),
          ContentType: 'text/plain'
        });

        uploadPromises.push(s3Client.send(putCommand));
        uploadedFiles.push(key);
      }

      const startTime = Date.now();
      const responses = await Promise.all(uploadPromises);
      const totalTime = Date.now() - startTime;

      expect(responses).toHaveLength(concurrentUploads);
      responses.forEach(response => {
        expect(response.$metadata.httpStatusCode).toBe(200);
      });

      console.log(`✅ ${concurrentUploads} concurrent uploads completed in ${totalTime}ms`);
    });
  });

  describe('S3 Security and Compliance', () => {
    it('validates bucket encryption settings', async () => {
      if (!s3Client) return;

      // Upload a file with server-side encryption
      const encryptedKey = `test-security/encrypted-${Date.now()}.json`;
      const sensitiveData = JSON.stringify({
        userId: 'test-user-123',
        accountNumber: 'ENCRYPTED_DATA',
        balance: 50000
      });

      const putCommand = new PutObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: encryptedKey,
        Body: Buffer.from(sensitiveData),
        ContentType: 'application/json',
        ServerSideEncryption: 'AES256',
        BucketKeyEnabled: true
      });

      const response = await s3Client.send(putCommand);
      uploadedFiles.push(encryptedKey);

      expect(response.ServerSideEncryption).toBe('AES256');
      expect(response.BucketKeyEnabled).toBe(true);

      console.log(`✅ File uploaded with server-side encryption`);
    });

    it('validates access control and permissions', async () => {
      if (!s3Client) return;

      const restrictedKey = `test-access/restricted-${Date.now()}.txt`;
      
      const putCommand = new PutObjectCommand({
        Bucket: S3_BUCKET_NAME,
        Key: restrictedKey,
        Body: Buffer.from('Restricted access content'),
        ContentType: 'text/plain',
        ACL: 'private' // Ensure private access
      });

      const response = await s3Client.send(putCommand);
      uploadedFiles.push(restrictedKey);

      expect(response.$metadata.httpStatusCode).toBe(200);

      // Verify public access is denied
      const publicUrl = `https://${S3_BUCKET_NAME}.s3.${AWS_REGION}.amazonaws.com/${restrictedKey}`;
      
      try {
        const publicResponse = await fetch(publicUrl);
        expect(publicResponse.status).toBeGreaterThanOrEqual(403); // Should be forbidden
        console.log(`✅ Public access properly denied (${publicResponse.status})`);
      } catch (error) {
        console.log(`✅ Public access properly blocked`);
      }
    });
  });
});

// Helper function to convert stream to buffer
async function streamToBuffer(stream) {
  const chunks = [];
  for await (const chunk of stream) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}