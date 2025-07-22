# Local Development Guide

## Fixed Issues ✅
1. **Navigation Error**: Fixed `Transition.Root` mismatch in navigation.jsx
2. **API Endpoint**: Updated vitest config to use correct API endpoint

## Quick Start - Use Your Existing Infrastructure

### Before Every Push (MANDATORY) 
```bash
# Simple one-command validation (lint + build)
npm run pre-push
```

### Development Workflow (Enhanced)
```bash
# 1. Setup development environment (your existing script)
npm run setup-dev

# 2. Start development 
npm run start               # Runs config + setup-dev + dev

# 3. Make your changes

# 4. Test locally (F12 console check)
# Open http://localhost:3000, check F12 console for errors

# 5. Pre-push validation  
npm run pre-push            # Lint + build validation

# 6. If validation passes, push safely
git add .
git commit -m "Your change description"  
git push origin initialbuild
```

### Your Existing Test Infrastructure (Use These!)

#### Pre-Push Validation (Consolidated!)
- `npm run pre-push` - Build validation (prevents F12 errors)
- `npm run lint` - Code quality check (warnings only)
- `npm run build` - Production build test

#### Your Comprehensive Test Suite (Available!)
- `npm run test:unit` - Unit tests with coverage
- `npm run test:integration:comprehensive` - Full integration tests
- `npm run test:e2e` - End-to-end Playwright tests
- `npm run test:all` - Complete test suite

#### Development (Your Scripts)
- `npm run start` - Full setup + dev server
- `npm run setup-dev` - Environment setup
- `npm run config` - API configuration

## Common Issues & Fixes

### Build Errors
- **Missing imports**: Check F12 console, add missing imports
- **Undefined variables**: Use eslint to find undefined vars
- **Component errors**: Check component prop types and imports

### API Connection Issues  
- API endpoint is configured to: `https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev`
- Check `public/config.js` and `.env.local` for correct URLs

### Quick Fixes
```bash
# Fix common linting issues
npm run lint:fix

# Clear build cache if needed
rm -rf dist/ && npm run build
```

## Why This Prevents F12 Errors

1. **Pre-push validation** catches build errors locally
2. **Linting** finds undefined variables and missing imports  
3. **Build test** verifies all components compile correctly
4. **Dev server test** ensures app starts without runtime errors

## The Problem We Solved

Before: Push → Deploy → Check F12 → Find errors → Fix → Push again
After: Check locally → Fix errors → Push once → No F12 errors in production