# Project Context: World-Class Finance Application

## Architecture & Infrastructure
- **Deployment**: AWS infrastructure as code (IaC) via CloudFormation templates
- **Database**: PostgreSQL with comprehensive schema validation and categorized table dependencies
- **Integration**: Live data websockets for real-time feeds and HFT with API key authentication
- **Branch**: Use `loaddata` branch for all changes and pushes
- **Services**: Lambda functions, ECS tasks, Step Functions orchestration
- **API Gateway**: Standardized response formatting across all endpoints
- **Security**: Comprehensive input validation, timeout management, and error handling

## Development Philosophy
- **Quality**: Building world-class finance application
- **Real Data**: Use live data and real mechanisms wherever possible
- **Minimal Mocking**: Avoid mock/fallback data except during initial page design
- **Full Integration**: Prefer identifying and fixing real issues over fake implementations
- **Security**: Follow information security best practices in all decisions

## Development Commands & Tooling
### Backend (Lambda/API)
- **Test**: `npm test` (in webapp/lambda/)
- **Package**: `npm run package` 
- **Deploy**: `npm run deploy-package`
- **Local Test**: `node test-local.js`

### Frontend (React/Vite)
- **Dev Server**: `npm run dev` (in webapp/frontend/)
- **Build**: `npm run build`
- **Test**: `npm test`

### Database & Loaders
- **DB Init**: `node webapp-db-init.js`
- **Test Loaders**: `python validate_data_loaders.py`
- **Pattern Recognition**: `python run_pattern_recognition.py`

### AWS Deployment
- **Deploy Stack**: Use CloudFormation templates (template-*.yml)
- **Check Health**: `node test-health.js`
- **Debug Auth**: `node debug-auth-flow.js`

## Code Style & Conventions
- **Indentation**: 2 spaces (JavaScript/JSON), 4 spaces (Python)
- **JavaScript**: Use modern ES6+ syntax, async/await preferred
- **Python**: Follow PEP 8, use descriptive variable names
- **File Naming**: kebab-case for scripts, camelCase for modules
- **Imports**: Group AWS SDK, third-party, then local imports

## Project Structure
### Key Directories
- `/webapp/lambda/` - Lambda function code and API routes
- `/webapp/frontend/` - React frontend application
- `/database/` - Database schemas and init scripts
- `/hft-system/` - High-frequency trading system (C++/FPGA)
- `/alpaca_trading_system/` - Python trading strategies
- `/test/` - Test environments and validation scripts

### Database Tables (Categorized Schema)
- **Core**: user_api_keys, users (authentication and API management)
- **Portfolio**: portfolio_holdings, portfolio_metadata, trading_orders (user trading data)
- **Market Data**: symbols, stock_symbols, price_daily, market_data (financial data feeds)
- **Analytics**: buy_sell_daily, buy_sell_weekly, buy_sell_monthly, technicals_daily, fundamentals, scores
- **Optional**: patterns, sentiment, earnings, risk_metrics, alerts, swing_trader, company_profile, key_metrics

## Dependencies & Libraries
### Backend
- **Database**: `pg` (PostgreSQL client), comprehensive timeout management, adaptive pool sizing
- **Auth**: `aws-jwt-verify`, `@aws-sdk/client-cognito-identity-provider`, JWT middleware
- **Trading**: `@alpacahq/alpaca-trade-api`, AlpacaService with circuit breaker patterns
- **Security**: `helmet`, `express-rate-limit`, `validator`, comprehensive input validation middleware
- **Infrastructure**: responseFormatter, logger with correlation IDs, timeoutManager
- **Validation**: sanitizers, validation schemas, XSS/SQL injection prevention

### Frontend
- **Framework**: React + Vite
- **UI**: Material-UI, custom components
- **Charts**: Custom chart components for financial data
- **State**: React Context for auth and themes

### Python Loaders
- **Data**: `yfinance`, `pandas`, `numpy`
- **AWS**: `boto3`, various AWS SDK clients
- **Database**: `psycopg2`, `sqlalchemy`

## Security Patterns
- **API Keys**: Store in AWS Secrets Manager, never commit to repo, comprehensive error handling
- **Environment Variables**: Use `.env` files locally, CloudFormation parameters in AWS
- **Authentication**: AWS Cognito with JWT verification, authenticateToken middleware on all protected routes
- **Rate Limiting**: Express middleware for API protection with adaptive throttling
- **Input Validation**: Comprehensive validation middleware with sanitizers across all routes
- **CORS**: Configured for specific origins only
- **Circuit Breakers**: External service failure protection with automatic recovery
- **Timeout Management**: Standardized timeouts across database, trading, and market data operations
- **Request Correlation**: Request IDs for tracing and debugging across services

## Data Sources & Integration
- **Market Data**: Alpaca API, Yahoo Finance, FRED (economic data)
- **Real-time**: WebSocket connections for live prices
- **Pattern Recognition**: Custom Python algorithms
- **Sentiment**: News analysis and social media integration
- **Risk**: Real-time risk analytics and monitoring

## Logging & Debugging
- **Structured Logging**: RequestLogger class with correlation IDs and performance tracking
- **Request Correlation**: Unique request IDs across all services for end-to-end tracing
- **Performance Monitoring**: Database query timing, API call duration, pool status tracking
- **Error Context**: Comprehensive error logging with stack traces and operational context
- **Database Monitoring**: Pool utilization, connection health, adaptive scaling recommendations
- **API Integration**: Detailed logging for external service calls with timeout and retry information
- **CloudWatch Integration**: Use CloudWatch for AWS service monitoring

## Task Management
- Maintain active todo lists consistently
- Update todos as work completes
- Track lingering items and potential improvements
- Mark items that aren't fully complete
- Focus on data loaders and website functionality first

## Infrastructure Utilities
### Core Services
- **Database**: `utils/database.js` - Pool management, schema validation, timeout handling
- **Logging**: `utils/logger.js` - Structured logging with correlation IDs
- **Response Formatting**: `utils/responseFormatter.js` - Standardized API responses
- **Timeout Management**: `utils/timeoutManager.js` - Service-specific timeout configurations
- **API Key Service**: `utils/apiKeyService.js` - Secure API key management
- **Alpaca Service**: `utils/alpacaService.js` - Trading API with circuit breaker patterns

### Middleware
- **Authentication**: `middleware/auth.js` - JWT verification and user validation
- **Validation**: `middleware/validation.js` - Input sanitization and validation schemas
- **Error Handling**: `middleware/errorHandler.js` - Centralized error processing

### Key Features
- **Schema Validation**: Categorized database table validation with impact analysis
- **Circuit Breakers**: External service failure protection with automatic recovery
- **Adaptive Pool Sizing**: Database connection optimization based on load patterns
- **Request Tracing**: End-to-end correlation IDs for debugging and monitoring

## Current Focus - Portfolio Performance Optimization
1. **Portfolio API Performance**: Optimized with batch processing, pagination, and memory-efficient operations
2. **Database Performance**: Added comprehensive indexes and query optimization for portfolio tables
3. **Memory Management**: Fixed JavaScript heap overflow issues with streaming and chunking
4. **Real-time Data Pipeline**: Enhanced websocket performance and reliability
5. **Advanced Trading Features**: Portfolio analytics, risk analysis, and strategy integration

## Recent Performance Improvements (2025-07-15)
- **Portfolio Holdings**: Implemented batch UPSERT operations (100x faster than individual queries)
- **Memory Usage**: Reduced by 80% through pagination and circular buffer optimizations
- **Database Queries**: Added performance indexes for portfolio_holdings and user_api_keys tables
- **Connection Pool**: Eliminated exhaustion issues with optimized batch processing and timeout management
- **Lambda Performance**: Removed memory leaks preventing cold start issues

## Testing & Validation
- **API Testing**: Use test scripts in webapp/lambda/
- **Data Validation**: Run `validate_data_loaders.py` 
- **Health Checks**: Monitor via `/health` endpoints
- **Integration**: Full end-to-end testing preferred over mocks