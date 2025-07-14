# Project Context: World-Class Finance Application

## Architecture & Infrastructure
- **Deployment**: AWS infrastructure as code (IaC) via CloudFormation templates
- **Database**: PostgreSQL with tables created via loader scripts or db-init file for site-specific tables
- **Integration**: Live data websockets for real-time feeds and HFT
- **Branch**: Use `loaddata` branch for all changes and pushes
- **Services**: Lambda functions, ECS tasks, Step Functions orchestration

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

### Database Tables
- **Core**: symbols, price_daily, technicals_daily, fundamentals
- **Analytics**: scores, patterns, sentiment, earnings
- **Trading**: portfolio, trades, alerts, risk_metrics
- **User**: Cognito integration, API keys, settings

## Dependencies & Libraries
### Backend
- **Database**: `pg` (PostgreSQL client)
- **Auth**: `aws-jwt-verify`, `@aws-sdk/client-cognito-identity-provider`
- **Trading**: `@alpacahq/alpaca-trade-api`
- **Security**: `helmet`, `express-rate-limit`, `validator`

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
- **API Keys**: Store in AWS Secrets Manager, never commit to repo
- **Environment Variables**: Use `.env` files locally, CloudFormation parameters in AWS
- **Authentication**: AWS Cognito with JWT verification
- **Rate Limiting**: Express middleware for API protection
- **Input Validation**: `validator` library for all user inputs
- **CORS**: Configured for specific origins only

## Data Sources & Integration
- **Market Data**: Alpaca API, Yahoo Finance, FRED (economic data)
- **Real-time**: WebSocket connections for live prices
- **Pattern Recognition**: Custom Python algorithms
- **Sentiment**: News analysis and social media integration
- **Risk**: Real-time risk analytics and monitoring

## Logging & Debugging
- Implement detailed logging wherever it makes sense
- Log comprehensively to solve problems effectively
- Better to over-log than fumble through blindly
- Use CloudWatch for AWS service monitoring
- Include request IDs for API tracing

## Task Management
- Maintain active todo lists consistently
- Update todos as work completes
- Track lingering items and potential improvements
- Mark items that aren't fully complete
- Focus on data loaders and website functionality first

## Current Focus
1. Get data loaders working correctly
2. Ensure website functionality  
3. Prepare for live data websocket integration
4. Maintain seamless AWS deployment compatibility
5. Build toward HFT system integration

## Testing & Validation
- **API Testing**: Use test scripts in webapp/lambda/
- **Data Validation**: Run `validate_data_loaders.py` 
- **Health Checks**: Monitor via `/health` endpoints
- **Integration**: Full end-to-end testing preferred over mocks