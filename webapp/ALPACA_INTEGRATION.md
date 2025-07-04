# Alpaca Integration Guide

This document provides comprehensive information about the Alpaca brokerage integration for portfolio analytics.

## Overview

The Alpaca integration allows users to:
- Securely connect their Alpaca brokerage accounts
- Import portfolio positions automatically
- Track real-time portfolio performance
- Analyze risk metrics and sector allocation
- View historical performance data

## Features

### 🔐 Secure API Key Management
- **AES-256-GCM Encryption**: All API keys encrypted before storage
- **User-Specific Salts**: Each user has unique encryption parameters
- **No Plaintext Logging**: API keys never appear in logs
- **Secure Deletion**: Complete key removal when disconnecting accounts

### 📊 Portfolio Data Import
- **Real-Time Positions**: Live portfolio holdings with current market values
- **P&L Tracking**: Unrealized gains/losses with percentage calculations
- **Historical Performance**: Up to 1 year of portfolio performance history
- **Account Information**: Cash balances, buying power, account status

### 📈 Analytics & Insights
- **Risk Metrics**: Volatility, Sharpe ratio, maximum drawdown, beta
- **Sector Allocation**: Automatic categorization and weight distribution
- **Performance Tracking**: Daily, weekly, monthly performance analysis
- **Activity History**: Recent trades, dividends, and account activities

### 🌐 Environment Support
- **Paper Trading**: Safe testing with Alpaca's paper trading environment
- **Live Trading**: Production support for real accounts
- **Environment Validation**: Clear indication of which environment is connected

## Getting Started

### Step 1: Get Alpaca API Keys

1. **Create an Alpaca Account**
   - Visit [Alpaca Markets](https://alpaca.markets/)
   - Sign up for a free account
   - Complete account verification if using live trading

2. **Generate API Keys**
   - Navigate to the Alpaca dashboard
   - Go to "Your API Keys" section
   - Generate new API keys
   - **Important**: Copy both the API Key and Secret Key immediately

3. **Choose Environment**
   - **Paper Trading** (Recommended for testing): Use paper trading keys
   - **Live Trading**: Use live trading keys (requires funded account)

### Step 2: Connect to Portfolio Analytics

1. **Navigate to Settings**
   - Log into the portfolio analytics application
   - Go to Settings → API Keys tab
   - Click "Add API Key"

2. **Configure Connection**
   - Select "Alpaca" as the broker
   - Enter your API Key and Secret Key
   - Choose "Sandbox Environment" for paper trading
   - Click "Add API Key"

3. **Test Connection**
   - Click the "Test Connection" button (🔑 icon)
   - Verify account information is displayed correctly
   - Confirm environment (Paper/Live) is correct

### Step 3: Import Portfolio

1. **Import Your Portfolio**
   - Click the "Import Portfolio" button (☁️ icon)
   - Wait for the import to complete
   - Review the imported positions and values

2. **Verify Data**
   - Navigate to the Portfolio page
   - Confirm all positions are displayed correctly
   - Check that P&L calculations match your Alpaca account

## API Integration Details

### Supported Alpaca APIs

The integration uses the following Alpaca API endpoints:

1. **Account Information** (`/v2/account`)
   - Account status and balances
   - Buying power and cash positions
   - Day trading information

2. **Positions** (`/v2/positions`)
   - Current holdings and quantities
   - Market values and cost basis
   - Unrealized P&L calculations

3. **Portfolio History** (`/v2/account/portfolio/history`)
   - Historical equity curves
   - Performance over time
   - Base value and profit/loss tracking

4. **Activities** (`/v2/account/activities`)
   - Recent trades and fills
   - Dividend payments
   - Other account activities

5. **Market Data** (`/v2/assets/{symbol}`)
   - Asset information and tradability
   - Exchange and class information

### Rate Limiting

The integration implements comprehensive rate limiting:
- **200 requests per minute per user**
- **Automatic retry with exponential backoff**
- **Error handling for API limits**
- **Request tracking and management**

### Error Handling

Robust error handling covers:
- Invalid API credentials
- Network connectivity issues
- Alpaca API rate limits
- Data validation errors
- Timeout scenarios

## Data Security

### Encryption Standards

- **Algorithm**: AES-256-GCM (Galois/Counter Mode)
- **Key Derivation**: scrypt with user-specific salts
- **Initialization Vector**: Random 16-byte IV per encryption
- **Authentication**: GCM provides built-in authentication tags

### Storage Security

```javascript
// Example of secure storage structure (implementation detail)
{
  encrypted_api_key: "hex_encoded_encrypted_data",
  encrypted_api_secret: "hex_encoded_encrypted_data",
  key_iv: "hex_encoded_initialization_vector",
  key_auth_tag: "hex_encoded_authentication_tag",
  secret_iv: "hex_encoded_initialization_vector",
  secret_auth_tag: "hex_encoded_authentication_tag",
  is_sandbox: true,
  created_at: "2024-01-01T00:00:00Z",
  last_used: "2024-01-01T12:00:00Z"
}
```

### Access Control

- **User Isolation**: Each user can only access their own API keys
- **JWT Authentication**: All requests require valid authentication
- **Audit Logging**: All key operations are logged (without sensitive data)
- **Automatic Cleanup**: Unused keys can be automatically removed

## Troubleshooting

### Common Issues

#### 1. Connection Test Fails

**Symptoms**: "Invalid Alpaca credentials" error

**Solutions**:
- Verify API keys are copied correctly (no extra spaces)
- Ensure you're using the correct environment (paper vs live)
- Check that Alpaca account is active and verified
- Confirm API keys haven't been revoked in Alpaca dashboard

#### 2. Import Returns No Positions

**Symptoms**: Import succeeds but shows 0 positions

**Possible Causes**:
- Account has no current positions
- Using paper trading account with no simulated trades
- API keys have limited permissions

**Solutions**:
- Add some positions to your Alpaca account
- Verify account has holdings in Alpaca dashboard
- Check API key permissions in Alpaca settings

#### 3. Portfolio Values Don't Match

**Symptoms**: Imported values differ from Alpaca dashboard

**Possible Causes**:
- Market hours vs. after-hours pricing
- Different price sources or timing
- Currency conversion issues

**Solutions**:
- Wait for market open to compare values
- Check timestamps of last update
- Verify account currency settings

#### 4. Rate Limiting Errors

**Symptoms**: "Rate limit exceeded" messages

**Solutions**:
- Wait 1 minute before retrying
- Reduce frequency of manual imports
- Contact support if persistent

### Diagnostic Tools

#### Test Connection Feature
Use the "Test Connection" button to diagnose issues:
- ✅ **Valid Connection**: Shows account ID and portfolio value
- ❌ **Invalid Credentials**: Check API keys and environment
- ⚠️ **Partial Data**: May indicate limited API permissions

#### CloudWatch Logs (Production)
For detailed debugging in production:
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/financial-dashboard-api \
  --filter-pattern "Alpaca" \
  --start-time $(date -d '1 hour ago' +%s)000
```

### Error Codes

| Error Code | Description | Solution |
|------------|-------------|----------|
| `401` | Invalid API credentials | Check API keys and environment |
| `403` | Insufficient permissions | Verify API key permissions in Alpaca |
| `429` | Rate limit exceeded | Wait and retry |
| `500` | Server error | Check CloudWatch logs, retry later |

## Advanced Configuration

### Custom Sector Mapping

The integration includes basic sector classification. For enhanced sector analysis:

```javascript
// Custom sector mapping can be added to alpacaService.js
const customSectorMap = {
  'AAPL': 'Technology',
  'TSLA': 'Electric Vehicles',
  'JPM': 'Financial Services',
  // Add your custom mappings
};
```

### Performance Optimization

For large portfolios:
- Enable database connection pooling
- Consider caching portfolio data
- Implement incremental updates
- Use background jobs for large imports

### Monitoring

Set up monitoring for:
- Import success rates
- API response times
- Error frequencies
- User activity patterns

## API Reference

### Endpoints

#### Test Connection
```http
POST /api/portfolio/test-connection/alpaca
Authorization: Bearer {jwt_token}
```

#### Import Portfolio
```http
POST /api/portfolio/import/alpaca
Authorization: Bearer {jwt_token}
```

#### Get Portfolio Analytics
```http
GET /api/portfolio/analytics
Authorization: Bearer {jwt_token}
```

### Response Formats

#### Import Success Response
```json
{
  "success": true,
  "message": "Portfolio imported successfully",
  "data": {
    "broker": "alpaca",
    "holdingsCount": 15,
    "totalValue": 125000.50,
    "importedAt": "2024-01-01T12:00:00Z",
    "summary": {
      "positions": 15,
      "cash": 5000.00,
      "totalPnL": 12500.50,
      "totalPnLPercent": 10.0,
      "dayPnL": 500.25,
      "dayPnLPercent": 0.4,
      "environment": "paper"
    }
  }
}
```

## Support

### Documentation
- [Alpaca API Documentation](https://alpaca.markets/docs/)
- [Portfolio Analytics User Guide](./USER_GUIDE.md)
- [Deployment Guide](./DEPLOYMENT_GUIDE.md)

### Getting Help
1. Check the troubleshooting section above
2. Review CloudWatch logs for detailed errors
3. Test connection using the built-in diagnostic tool
4. Verify Alpaca account status and API key permissions

### Contributing
To improve the Alpaca integration:
1. Review the `alpacaService.js` implementation
2. Add test cases for new features
3. Update documentation for any changes
4. Follow security best practices for handling API keys

## Compliance and Legal

### Data Handling
- Portfolio data is stored securely with encryption
- User data is isolated and access-controlled
- API keys are encrypted and never logged
- Data retention policies can be configured

### Alpaca Terms
- Users must comply with Alpaca's Terms of Service
- API usage must follow Alpaca's acceptable use policies
- Rate limiting respects Alpaca's API guidelines

### Financial Regulations
- This integration is for informational purposes only
- Not intended as investment advice
- Users responsible for their own trading decisions
- Portfolio analytics for educational and tracking purposes

---

**Note**: Always test with paper trading accounts before connecting live trading accounts. This integration handles sensitive financial data and should be deployed with appropriate security measures.