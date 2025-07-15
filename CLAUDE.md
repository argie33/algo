# Project Context: World-Class Finance Application

## Architecture & Infrastructure - PRODUCTION READY
- **Deployment**: AWS infrastructure as code (IaC) via CloudFormation templates with comprehensive error handling
- **Database**: PostgreSQL with comprehensive schema validation, categorized table dependencies, and performance monitoring
- **Integration**: Live data websockets for real-time feeds and HFT with per-user API key authentication
- **Branch**: Use `loaddata` branch for all changes and pushes
- **Services**: Lambda functions, ECS tasks, Step Functions orchestration with full observability
- **API Gateway**: Standardized response formatting across all endpoints with CORS resolution
- **Security**: Comprehensive input validation, timeout management, error handling, and route protection
- **Monitoring**: Real-time performance monitoring with alerts, metrics tracking, and system health dashboards

## Development Philosophy - BATTLE-TESTED
- **Quality**: Building world-class finance application with institutional-grade reliability
- **Real Data**: Use live data and real mechanisms - ALL MOCK DATA ELIMINATED
- **User Experience**: Proper onboarding flows with graceful degradation for users without API keys
- **Full Integration**: Prefer identifying and fixing real issues over fake implementations
- **Security**: Follow information security best practices in all decisions with defense in depth
- **Observability**: Comprehensive monitoring, logging, and alerting for production operations

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

## Critical Architectural Issues Fixed
### Database Initialization Deployment
- **Issue**: Conflicting Dockerfiles (`Dockerfile.dbinit` vs `Dockerfile.webapp-db-init`)
- **Fix**: Use correct `Dockerfile.webapp-db-init` with Node.js script
- **Integration**: Database initialization ECS task properly integrated into deployment workflow
- **Impact**: Resolves API key service failures across settings, portfolio, live data, and trade history pages

### Multi-User API Key Architecture
- **Architecture**: Per-user API key retrieval from database with AES-256-GCM encryption
- **Service**: `utils/apiKeyService.js` handles encrypted key management
- **Security**: Each user's API keys stored with individual salt and encryption keys

### CORS Configuration
- **Issue**: Multiple conflicting CORS middleware causing 502 errors
- **Fix**: Consolidated into single CORS configuration with dynamic origin detection
- **Location**: `webapp/lambda/index.js` unified CORS middleware

## Current Focus
1. **Database initialization deployment architecture** - Fix conflicting Dockerfiles and missing deployment integration
2. User onboarding UX for graceful degradation when API keys are missing
3. Real-time websocket performance and reliability
4. Advanced trading strategy integration
5. Performance monitoring and alerting

## 4 Core Documentation System - CRITICAL
The project is driven by 4 core documents that must be continuously updated and reviewed:

### 1. **FINANCIAL_PLATFORM_BLUEPRINT.md** - Technical Blueprint
- **Purpose**: Comprehensive technical blueprint for building institutional-grade financial analysis platform
- **Usage**: Reference for all technical decisions, scoring algorithms, and system architecture
- **Update When**: New features planned, architecture changes, or technical requirements evolve

### 2. **DEVELOPMENT_TASKS.md** - Task List & Progress Tracker
- **Purpose**: Real-time development progress tracking and TODO management
- **Usage**: Primary source for current work priorities, bug tracking, and implementation status
- **Update When**: Tasks completed, new issues discovered, priorities changed, or session terminated
- **CRITICAL**: Must be updated continuously throughout development sessions

### 3. **TEST_PLAN.md** - Testing Strategy
- **Purpose**: Comprehensive testing framework for all system components
- **Usage**: Guide for test implementation, quality assurance, and system validation
- **Update When**: New features added, bugs discovered, or testing requirements change

### 4. **DESIGN.md** - System Design Document
- **Purpose**: Advanced technical architecture and implementation details
- **Usage**: Reference for system design decisions, performance optimizations, and scalability patterns
- **Update When**: Architecture changes, performance improvements, or new system components added

### Documentation Management Commands
- **Read All 4 Docs**: Start each session by reviewing all 4 documents
- **Update Progress**: Continuously update DEVELOPMENT_TASKS.md with current status
- **Sync Requirements**: Ensure all 4 docs align with current system state
- **Reference First**: Always check relevant docs before making technical decisions

## Task Management
- Maintain active todo lists consistently
- Update todos as work completes
- Track lingering items and potential improvements
- Mark items that aren't fully complete
- Focus on infrastructure stability and website functionality first

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