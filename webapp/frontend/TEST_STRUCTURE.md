# Test Structure for AWS Deployment

## Overview

Our testing is split into two environments:

1. **Local Development Tests** (`npm run test:local`)
   - Unit tests for components, services, and utilities
   - Fast feedback during development
   - No external API calls or real AWS services
   - Runs in 15-30 seconds

2. **AWS Integration Tests** (`npm run test:aws`)
   - Integration tests for AWS Lambda functions
   - End-to-end workflow testing
   - Mocked AWS services (DynamoDB, S3, Lambda)
   - Runs in AWS CI/CD pipeline

## Local Development Testing

```bash
# Run all local tests (default)
npm test

# Run local tests with coverage
npm run test:coverage

# Run only unit tests
npm run test:unit
```

**What runs locally:**
- `src/tests/unit/**/*.test.{js,jsx}` - Component and service unit tests
- `src/tests/integration/simple-integration.test.js` - Basic integration tests
- `src/tests/integration/validation-real-calculations.test.js` - Math validation tests
- `src/tests/integration/*-aws-routes.test.js` - AWS route logic tests

## AWS Integration Testing

```bash
# Run AWS integration tests (for CI/CD)
npm run test:aws

# Run AWS integration tests locally (for debugging)
npm run test:integration
```

**What runs in AWS:**
- `src/tests/integration/aws/**/*.test.js` - AWS service integration tests
- `src/tests/integration/workflows/**/*.test.js` - End-to-end workflow tests
- `src/tests/e2e/**/*.test.js` - Full application end-to-end tests

## File Structure

```
src/tests/
├── unit/                          # Local unit tests
│   ├── components/               # React component tests
│   ├── services/                 # Service logic tests
│   └── pages/                    # Page component tests
├── integration/
│   ├── simple-integration.test.js         # Basic local integration
│   ├── validation-real-calculations.test.js # Math validation (local)
│   ├── *-aws-routes.test.js              # AWS route logic (local)
│   ├── aws/                              # AWS-specific integration tests
│   │   ├── lambda-functions.test.js      # Lambda function tests
│   │   ├── dynamodb-integration.test.js  # DynamoDB tests
│   │   └── api-gateway.test.js           # API Gateway tests
│   └── workflows/                        # End-to-end workflows
│       ├── user-journey.test.js          # Complete user workflows
│       └── trading-workflow.test.js      # Trading process tests
└── setup/
    ├── setup.js                  # Local test setup
    └── aws-setup.js             # AWS test setup
```

## Configuration Files

- `vitest.config.local.js` - Local development test configuration
- `vitest.config.aws.js` - AWS integration test configuration
- `vitest.config.js` - Default configuration (points to local)

## Why This Structure?

### The Problem We Solved
Previously, we had integration tests trying to make real HTTP requests, connect to live databases, and call external APIs during local development. This caused:
- Slow test runs (60+ seconds)
- Network dependency failures
- API rate limiting issues
- Tests that only worked with specific credentials

### The Solution
1. **Local tests** focus on logic, components, and calculations without external dependencies
2. **AWS tests** run in the actual deployment environment where external calls make sense
3. **Clear separation** prevents confusion about what should run where
4. **Fast feedback** for developers (local tests run in <30 seconds)
5. **Comprehensive validation** in CI/CD (AWS tests validate real integration)

## Usage in CI/CD

Your AWS workflow should run:
```bash
npm run test:local    # Quick validation of logic
npm run test:aws      # Full integration testing
```

This ensures both fast development feedback and comprehensive deployment validation.