# Environment Configuration Guide

This document explains how to configure the Financial Dashboard frontend for different environments (development, staging, production).

## Overview

The frontend uses a multi-layered configuration system:

1. **Runtime Configuration** (`public/config.js`) - Loaded at runtime, can be overridden
2. **Build-time Environment Variables** (`.env` files) - Set during build process
3. **Vite Configuration** (`vite.config.js`) - Development server and build settings

## Quick Start

### Development

```
npm run setup-dev
npm run dev
```

### Production/Deployed Environment (dev, staging, prod)

Set the API URL and environment name:

```
# For dev deployment
npm run setup-prod -- "https://your-api-gateway-url.amazonaws.com/dev" dev

# For staging deployment
npm run setup-prod -- "https://your-api-gateway-url.amazonaws.com/staging" staging

# For production deployment
npm run setup-prod -- "https://your-api-gateway-url.amazonaws.com/prod" production

npm run build
# Deploy dist/ to S3/CloudFront
```

- The scripts will update both `public/config.js` and `.env` for Vite.
- The frontend will always use the correct API URL for the current environment.
- You can add more environments as needed.

## Environment Configuration

### Development Environment

- **API URL**: `http://localhost:3001`
- **Serverless**: `false`
- **Debug**: `true`
- **Mock Data**: `false`

### Production Environment

- **API URL**: Your API Gateway URL
- **Serverless**: `true`
- **Debug**: `false`
- **Mock Data**: `false`

## Configuration Files

### 1. Runtime Configuration (`public/config.js`)

This file is loaded by the browser and can be dynamically updated:

```javascript
window.__CONFIG__ = {
  API_URL: "http://localhost:3001", // or your production API URL
  BUILD_TIME: "2024-01-01T00:00:00.000Z",
  VERSION: "1.0.0",
  ENVIRONMENT: "development", // or "production"
};
```

### 2. Environment Variables (`.env`)

Vite environment variables for build-time configuration:

```bash
# API Configuration
VITE_API_URL=http://localhost:3001
VITE_SERVERLESS=false
VITE_ENVIRONMENT=development

# Build Configuration
VITE_BUILD_TIME=2024-01-01T00:00:00.000Z
VITE_VERSION=1.0.0

# Feature Flags
VITE_ENABLE_DEBUG=true
VITE_ENABLE_MOCK_DATA=false
```

### 3. Vite Configuration (`vite.config.js`)

Development server proxy and build settings:

```javascript
server: {
  port: 3000,
  proxy: {
    '/api': {
      target: 'http://localhost:3001', // Development API
      changeOrigin: true,
      timeout: 45000
    }
  }
}
```

## API URL Resolution Priority

The frontend resolves the API URL in this order:

1. **Runtime Config** (`window.__CONFIG__.API_URL`)
2. **Build-time Env Var** (`VITE_API_URL`)
3. **Development Fallback** (`http://localhost:3001`)
4. **Production Fallback** (empty string - should be set)

## Deployment Scripts

### Local Development

```bash
# Set up development environment
npm run setup-dev

# Start development server
npm run dev
```

### Production Build

```bash
# Set up production environment
npm run setup-prod https://your-api-url.com

# Build for production
npm run build-prod
```

### Serverless Deployment

```bash
# Deploy to AWS Lambda + API Gateway
cd webapp
./deploy-serverless.sh dev
```

### CloudFormation Deployment

```bash
# Deploy with dynamic API URL from CloudFormation
cd webapp/frontend
./build-dynamic.sh financial-dashboard-dev dev
```

## Troubleshooting

### API Connection Issues

1. **Check API URL Configuration**:

   ```javascript
   // In browser console
   console.log(window.__CONFIG__);
   console.log(import.meta.env.VITE_API_URL);
   ```

2. **Verify Backend Server**:

   ```bash
   # Test API health
   curl http://localhost:3001/health
   ```

3. **Check Environment Setup**:
   ```bash
   # Verify configuration
   npm run setup-dev
   cat .env
   cat public/config.js
   ```

### Common Issues

1. **Mixed Environment Configurations**:
   - Ensure all configuration files point to the same environment
   - Run setup scripts to reset configuration

2. **CORS Issues**:
   - Development: Vite proxy handles CORS
   - Production: Ensure API Gateway CORS is configured

3. **Build Failures**:
   - Clear `node_modules` and reinstall: `rm -rf node_modules && npm install`
   - Check environment variables are set correctly

## Environment-Specific Features

### Development Features

- Hot module replacement
- Source maps
- Debug logging
- API proxy to localhost
- Mock data support (optional)

### Production Features

- Optimized builds
- Minified code
- CDN caching
- Error tracking
- Performance monitoring

## Security Considerations

1. **Environment Variables**: Never commit `.env` files with secrets
2. **API Keys**: Use environment variables for sensitive data
3. **CORS**: Configure properly for production domains
4. **HTTPS**: Always use HTTPS in production

## Migration Guide

### From Old Configuration

If you're migrating from the old configuration system:

1. **Backup current config**:

   ```bash
   cp public/config.js public/config.js.backup
   ```

2. **Set up new environment**:

   ```bash
   npm run setup-dev  # for development
   # or
   npm run setup-prod https://your-api-url.com  # for production
   ```

3. **Test configuration**:

   ```bash
   npm run dev  # test development
   npm run build-prod  # test production build
   ```

4. **Update deployment scripts** if needed

## Support

For issues with environment configuration:

1. Check this README
2. Review the setup scripts in `scripts/`
3. Check browser console for configuration logs
4. Verify API connectivity with the ServiceHealth page
