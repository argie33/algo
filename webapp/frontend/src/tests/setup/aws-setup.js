/**
 * AWS Integration Test Setup
 * Configuration for tests that run in AWS CI/CD pipeline
 */

import { beforeAll, beforeEach, afterEach, afterAll, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';

// Global test environment setup for AWS
beforeAll(() => {
  console.log('🌩️ AWS Integration Test Environment Setup');
  
  // Set AWS-specific environment variables
  process.env.NODE_ENV = 'test';
  process.env.AWS_INTEGRATION = 'true';
  process.env.SKIP_LOCAL_TESTS = 'true';
  
  // Mock AWS SDK for integration tests
  vi.mock('@aws-sdk/client-dynamodb', () => ({
    DynamoDBClient: vi.fn(() => ({
      send: vi.fn()
    })),
    QueryCommand: vi.fn(),
    PutItemCommand: vi.fn(),
    UpdateItemCommand: vi.fn(),
    DeleteItemCommand: vi.fn()
  }));
  
  vi.mock('@aws-sdk/client-s3', () => ({
    S3Client: vi.fn(() => ({
      send: vi.fn()
    })),
    GetObjectCommand: vi.fn(),
    PutObjectCommand: vi.fn()
  }));
  
  vi.mock('@aws-sdk/client-lambda', () => ({
    LambdaClient: vi.fn(() => ({
      invoke: vi.fn()
    })),
    InvokeCommand: vi.fn()
  }));
  
  // Mock external API calls that shouldn't run in AWS tests
  vi.mock('axios', () => ({
    default: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      create: vi.fn(() => ({
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn()
      }))
    }
  }));
  
  // Mock WebSocket for AWS environment
  global.WebSocket = vi.fn(() => ({
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    send: vi.fn(),
    close: vi.fn(),
    readyState: 1, // OPEN
    CONNECTING: 0,
    OPEN: 1,
    CLOSING: 2,
    CLOSED: 3
  }));
  
  console.log('✅ AWS test environment configured');
});

beforeEach(() => {
  // Clear all mocks before each test
  vi.clearAllMocks();
  
  // Reset any DOM state
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

afterEach(() => {
  // Cleanup after each test
  cleanup();
  vi.restoreAllMocks();
});

afterAll(() => {
  console.log('🌩️ AWS Integration Test Environment Cleanup');
});

// AWS-specific test utilities
export const awsTestUtils = {
  // Mock AWS Lambda response
  mockLambdaResponse: (statusCode = 200, body = {}) => ({
    statusCode,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*'
    },
    body: JSON.stringify(body)
  }),
  
  // Mock DynamoDB response
  mockDynamoResponse: (items = []) => ({
    Items: items,
    Count: items.length,
    ScannedCount: items.length
  }),
  
  // Mock API Gateway event
  mockApiGatewayEvent: (httpMethod = 'GET', path = '/', body = null) => ({
    httpMethod,
    path,
    headers: {
      'Content-Type': 'application/json'
    },
    body: body ? JSON.stringify(body) : null,
    requestContext: {
      requestId: 'test-request-id',
      stage: 'test',
      identity: {
        sourceIp: '127.0.0.1'
      }
    }
  }),
  
  // Wait for AWS operations
  waitForAWSOperation: (ms = 1000) => new Promise(resolve => setTimeout(resolve, ms))
};

export default awsTestUtils;