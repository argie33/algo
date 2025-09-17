# Authentication Guide for Development

The Trade History page requires authentication to display trade data. Here's how to authenticate in the development environment:

## Quick Fix - Development Login

1. **Navigate to the frontend**: Open http://localhost:5176 in your browser
2. **Go to Login page**: Look for a Login/Sign In button or navigate to `/login` or `/auth`
3. **Use development credentials**:
   - **Email**: `argeropolos@gmail.com`
   - **Username**: `devuser` (either email or username works)
   - **Password**: `password123`

## What's Happening

The app is running in development mode with a dev authentication system that creates a default user automatically. The Trade History page checks for authentication and shows:
- "Please log in to view your trade history" if not authenticated
- "No authentication token available" if the user object exists but has no token

## API Testing Results

✅ **Working**: Trade history API endpoint returns 14 trade records
✅ **Working**: Authentication with `dev-bypass-token`
⚠️  **Issues**: Some secondary endpoints need fixes but the core functionality works

## Trade History Data Available

The system has sample trade data with 14 trades including:
- AAPL, MSFT, GOOGL, SPY, QQQ, TSLA, NVDA, VTI, BND
- Mix of buy orders from 2024-2025
- P&L data and execution times

## Next Steps After Login

Once logged in, the Trade History page should display:
- **Trade List**: Sortable table with all trades
- **Performance Chart**: P&L visualization over time
- **Analytics**: Trading statistics and metrics
- **AI Insights**: Trading pattern analysis

The authentication token will be stored and used for all API calls to fetch your trading data.