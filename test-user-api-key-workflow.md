# User API Key Addition Workflow Test Guide

## Deployment Status: ✅ SUCCESSFUL

The deployment has been completed successfully with the following verified components:

### ✅ Infrastructure Status
- **API Gateway**: Operational at `https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev`
- **Lambda Function**: Version 10.1.0, responding correctly
- **Database**: PostgreSQL 17.4, fully connected with 40 tables
- **Authentication**: Working correctly (returns 401 for protected endpoints)
- **Tables**: All required tables present including `user_api_keys`, `users`, `portfolio_holdings`

### ✅ API Endpoints Verified
- `GET /` - API info and version ✅
- `GET /health` - Database connectivity ✅
- `GET /health?quick=true` - Quick health check ✅
- `GET /api/settings/api-keys` - Authentication required ✅
- `GET /api/stocks` - Authentication required ✅
- `GET /api/portfolio` - Authentication required ✅

## 🔑 User API Key Addition Workflow

### Manual Testing Steps

Since the API requires authentication, here's how to test the user API key addition workflow:

#### 1. **Access the Frontend Application**
```bash
# The frontend should be deployed at the CloudFront URL
# Check the GitHub Actions logs for the actual URL
# Example: https://d123456789.cloudfront.net
```

#### 2. **User Registration/Login**
```bash
# Navigate to the frontend application
# Register a new user or login with existing credentials
# The Cognito authentication should be working
```

#### 3. **Access Settings Page**
```bash
# Navigate to Settings page in the frontend
# Should see API Key configuration section
# This tests the Settings.jsx component
```

#### 4. **Add API Key**
```bash
# Test adding an Alpaca API key:
# 1. Select "Alpaca" as provider
# 2. Enter API key (use paper trading key for testing)
# 3. Enter API secret
# 4. Click "Save" or "Add Key"
```

#### 5. **Test API Key Storage**
```bash
# Expected behavior:
# - API key should be encrypted and stored in user_api_keys table
# - User should see confirmation message
# - API key should appear in the settings list (masked)
```

#### 6. **Test API Key Retrieval**
```bash
# Navigate to Portfolio page
# Try to import portfolio data
# This should:
# - Retrieve the encrypted API key from database
# - Decrypt it using the encryption secret
# - Use it to call Alpaca API
# - Import and display portfolio data
```

### 🧪 Technical Testing (Backend)

#### Test Database Schema
```sql
-- Connect to database and verify table structure
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'user_api_keys';

-- Expected columns:
-- id (uuid)
-- user_id (varchar)
-- provider (varchar)
-- api_key_encrypted (text)
-- api_secret_encrypted (text)
-- iv (varchar)
-- auth_tag (varchar)
-- created_at (timestamp)
-- updated_at (timestamp)
-- is_active (boolean)
-- key_name (varchar)
-- environment (varchar)
```

#### Test API Endpoints (with authentication)
```bash
# Get JWT token from frontend login
export JWT_TOKEN="your-jwt-token-here"

# Test GET API keys
curl -H "Authorization: Bearer $JWT_TOKEN" \
     "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/settings/api-keys"

# Test POST API key
curl -X POST \
     -H "Authorization: Bearer $JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "provider": "alpaca",
       "apiKey": "your-test-api-key",
       "apiSecret": "your-test-api-secret",
       "environment": "paper"
     }' \
     "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/settings/api-keys"
```

### 🎯 Success Criteria

#### ✅ API Key Addition
- [ ] User can access Settings page
- [ ] API key form is displayed correctly
- [ ] API key can be added with proper validation
- [ ] API key is encrypted and stored in database
- [ ] User sees confirmation message
- [ ] API key appears in settings list (masked)

#### ✅ API Key Retrieval
- [ ] Portfolio page can retrieve API key
- [ ] API key is decrypted successfully
- [ ] Alpaca API connection works
- [ ] Portfolio data is imported and displayed
- [ ] Error handling works for invalid keys

#### ✅ Security
- [ ] API keys are encrypted in database
- [ ] API keys are never logged in plain text
- [ ] Authentication is required for all API key operations
- [ ] User can only access their own API keys

### 🐛 Troubleshooting

#### Common Issues:
1. **403 Forbidden**: Check authentication token
2. **401 Unauthorized**: Token may be expired
3. **500 Internal Server Error**: Check Lambda logs
4. **Database Connection Error**: Check RDS connectivity
5. **Encryption Error**: Check API_KEY_ENCRYPTION_SECRET_ARN

#### Debug Commands:
```bash
# Check Lambda logs
aws logs tail /aws/lambda/financial-dashboard-api-dev --follow

# Check database connectivity
curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health"

# Check diagnostics
curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/diagnostics"
```

### 📋 Test Results Template

```
Date: ___________
Tester: ___________

Frontend Tests:
[ ] Can access frontend application
[ ] User registration/login works
[ ] Settings page loads correctly
[ ] API key form is functional
[ ] API key can be added successfully
[ ] API key appears in settings list

Backend Tests:
[ ] API key is encrypted in database
[ ] API key can be retrieved and decrypted
[ ] Portfolio import works with API key
[ ] Authentication is enforced
[ ] Error handling works correctly

Issues Found:
_________________________________
_________________________________
_________________________________

Overall Status: [ ] PASS [ ] FAIL
```

## 🚀 Next Steps

1. **Manual Testing**: Follow the workflow above to test API key addition
2. **End-to-End Testing**: Test complete user journey from registration to portfolio import
3. **Performance Testing**: Test with multiple API keys and users
4. **Security Testing**: Verify encryption and access controls
5. **Error Handling**: Test various error scenarios

## 📊 Current Status

**Deployment**: ✅ Complete and operational
**Infrastructure**: ✅ All components working
**Database**: ✅ All tables initialized
**Authentication**: ✅ Working correctly
**API Endpoints**: ✅ Responding as expected

**Ready for**: User API key workflow testing and end-to-end validation