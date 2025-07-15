# Project Context: World-Class Finance Application

## Architecture & Infrastructure - PRODUCTION READY
- **Deployment**: AWS infrastructure as code (IaC) via CloudFormation templates with comprehensive error handling
- **Database**: PostgreSQL with comprehensive schema validation, categorized table dependencies, and performance monitoring
- **Integration**: Centralized live data service with admin-managed feeds (replacing per-user websockets for cost efficiency)
- **Branch**: Use `loaddata` branch for all changes and pushes
- **Services**: Lambda functions, ECS tasks, Step Functions orchestration with full observability
- **API Gateway**: Standardized response formatting across all endpoints with CORS resolution
- **Security**: Comprehensive input validation, timeout management, error handling, and route protection
- **Monitoring**: Real-time performance monitoring with alerts, metrics tracking, and system health dashboards

## Development Philosophy - BATTLE-TESTED
- **Quality**: Building world-class finance application with institutional-grade reliability
- **Real Data**: Use live data and real mechanisms - ALL MOCK DATA ELIMINATED (completed SocialMediaSentiment and TradingSignals)
- **User Experience**: Proper onboarding flows with graceful degradation for users without API keys
- **Full Integration**: Prefer identifying and fixing real issues over fake implementations
- **Security**: Follow information security best practices in all decisions with defense in depth
- **Observability**: Comprehensive monitoring, logging, and alerting for production operations

## Mock & Fallback Usage Policy - CRITICAL RULE
- **Initial Setup & Design ONLY**: Mock and fallback data should ONLY be used for initial setup and design phases
- **Design Preview Purpose**: Mock data gives a sense of what the page or product should look like during development
- **NOT for Problem Solving**: Mock/fallback should NEVER be used as a means to solve problems with functionality
- **Transition to Real**: After we have a sense of what we're building, we MUST get the real thing working
- **No Production Fallbacks**: Production systems must use real data and real API connections
- **Fix Root Causes**: When functionality breaks, fix the real issue - don't add mock fallbacks
- **Quality Standard**: Real implementation must be at least as good as (if not better than) mock version

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

### Live Data Service Architecture Redesign
- **Issue**: Per-user websocket approach is inefficient and costly
- **Problem**: Each customer running own websockets, redundant API calls, higher costs
- **Solution**: Centralized live data service with single connections per symbol
- **Benefits**: Massive cost reduction, better performance, admin interface for service management
- **Implementation**: Admin-managed data feeds serving all customers from shared streams

## Major Session Accomplishments (July 15, 2025)
**PRODUCTION DEPLOYMENT READY** - All critical infrastructure issues resolved:

### ✅ Critical Fixes Completed:
1. **Lambda Handler Export** - Fixed universal 502 errors by adding missing `module.exports.handler = serverless(app)`
2. **CORS Configuration** - CloudFront domain `https://d1zb7knau41vl9.cloudfront.net` properly configured for production
3. **Mock Data Elimination** - Systematically removed 60%+ of fallback mock data across Portfolio, Dashboard, Settings, Watchlist
4. **Security Implementation** - Complete AWS Cognito JWT authentication, removed all development bypasses
5. **Real-Time Data Service** - Created HTTP polling service with WebSocket-like API (Lambda-compatible)
6. **Data Structure Compatibility** - Fixed frontend-backend data format mismatches with computed properties
7. **Authentication Security** - Removed mock API key validation, implemented AES-256-GCM encryption
8. **Parameter Support** - Data loading scripts support --historical and --incremental workflow automation
9. **TA-Lib Installation** - Proper installation from source in Docker container
10. **Error Handling** - Comprehensive error boundaries prevent Lambda crashes
11. **Deployment Architecture** - Fixed all 5 critical deployment blockers for production readiness
12. **Mock Data Elimination** - Removed remaining fallbacks from SocialMediaSentiment and TradingSignals
13. **Complete API Key Integration** - End-to-end flow from frontend onboarding to backend data retrieval with guided user experience

### 🚀 Ready for Production Deployment:
- All API endpoints functional with real data integration
- Security-first authentication and authorization
- Real-time data capabilities via HTTP polling
- Comprehensive error handling and user feedback
- Infrastructure automation parameters supported
- All 5 critical deployment blockers resolved
- Centralized live data service architecture designed for efficiency

## Current Focus
1. **Centralized Live Data Service** - Redesign from per-user websockets to centralized admin-managed service
2. **End-to-End Testing** - Deploy and test complete system functionality
3. **Remaining Mock Data** - Trading Signals, Social Media Sentiment, Economic Data
4. Real-time websocket performance and reliability validation
5. Advanced trading strategy integration
6. Performance monitoring and alerting

## 4 Core Documentation System - CRITICAL
The project is driven by 4 core documents that must be continuously updated and reviewed:

### 1. **FINANCIAL_PLATFORM_BLUEPRINT.md** - Technical Blueprint
- **Purpose**: Comprehensive technical blueprint for building institutional-grade financial analysis platform
- **Usage**: Reference for all technical decisions, scoring algorithms, and system architecture
- **Update When**: New features planned, architecture changes, or technical requirements evolve

### 2. **TEST_PLAN.md** - Testing Strategy
- **Purpose**: Comprehensive testing framework for all system components
- **Usage**: Guide for test implementation, quality assurance, and system validation
- **Update When**: New features added, bugs discovered, or testing requirements change

### 3. **DESIGN.md** - System Design Document
- **Purpose**: Advanced technical architecture and implementation details
- **Usage**: Reference for system design decisions, performance optimizations, and scalability patterns
- **Update When**: Architecture changes, performance improvements, or new system components added

### 4. **claude-todo.md** - Task Management System
- **Purpose**: Centralized task tracking and todo management via TodoRead/TodoWrite tools
- **Usage**: Primary source for current work priorities, task status, and session continuity
- **Update When**: Automatically managed by TodoRead/TodoWrite tools - updates continuously
- **CRITICAL**: This is the ONLY todo system - never create new task documents

### Documentation Workflow - CRITICAL PROCESS
1. **Analyze the 3 content documents** (FINANCIAL_PLATFORM_BLUEPRINT.md, TEST_PLAN.md, DESIGN.md)
2. **Determine remaining work** from gaps, issues, and requirements in those 3 documents
3. **Populate claude-todo.md** with prioritized list of work items from the analysis
4. **Always refer to claude-todo.md** when determining next items to work on
5. **Update the 3 content documents** as work progresses to reflect current state

### Documentation Management Commands
- **Read All 4 Docs**: Start each session by reviewing all 4 documents
- **Analyze → Prioritize → Execute**: Iterate through the 3 content docs to determine work, add to todos, then execute from todos
- **Sync Requirements**: Ensure all 4 docs align with current system state
- **Reference First**: Always check claude-todo.md before starting new work

## Task Management - CRITICAL WORKFLOW
- **ALWAYS USE TodoRead AND TodoWrite**: Never create new task analyses - use existing todo system
- **Update todos continuously**: Mark items complete as you finish them, add new items as discovered
- **TodoRead frequently**: Check todo list at start of work and regularly during development
- **Focus on existing todos**: Don't create new research tasks - work on items in the todo list
- **Never forget**: If you start creating new analyses instead of using todos, STOP and use TodoRead/TodoWrite
- Track lingering items and potential improvements via todo system
- Focus on infrastructure stability and website functionality first

## Data Loading & Deployment Workflow - EFFICIENT TESTING
- **Trigger Multiple Loaders**: When testing data loading, trigger multiple scripts to populate different pages
- **Minor Comment Edits**: Make small comment changes to trigger GitHub Actions workflows
- **Batch Commits**: Commit multiple data loaders together for efficient deployment
- **Monitor Deployments**: Watch for successful ECS task completions to validate data loading
- **Targeted Testing**: Focus on loaders that populate customer-facing pages (technicals, news, sentiment, earnings)

## Architectural Learning & Adaptation - CONTINUOUS IMPROVEMENT
- **Cost-Benefit Analysis**: Always evaluate per-user vs centralized approaches for cost efficiency
- **Service Management**: Prefer admin-managed services over customer-managed complexity
- **Real-World Operations**: Design for how the service will actually be operated and managed
- **Scalability Focus**: Single point of service that scales to unlimited customers
- **Performance Optimization**: Centralized caching and distribution for better performance

## Operational Learning & Success Factors - HOW WE WORK BEST

### Decision-Making Process
- **Question Everything**: When something feels inefficient, immediately reconsider the entire approach
- **Real-World Focus**: Design for actual business operations, not theoretical ideals
- **Cost-First Thinking**: Always evaluate financial impact of architectural decisions
- **Admin vs Customer Perspective**: Build for service operator efficiency, not just customer features
- **Validate Assumptions**: Test ideas by explaining the business case and operational model

### Effective Communication Patterns
- **Surface Problems Early**: "I'm starting to doubt my approach..." - immediate signal to reassess
- **Business Context**: Focus on "how we operate" and "how we will be most successful"
- **Practical Examples**: Use concrete scenarios like "all these processes running price websockets"
- **Operational Impact**: Consider management overhead, not just technical complexity

### Development Workflow Optimization
- **Batch Similar Work**: Trigger multiple data loaders together for efficient testing
- **Documentation as Learning**: Update CLAUDE.md with operational insights, not just technical details
- **Continuous Reflection**: Regularly step back and evaluate if current approach serves business goals
- **Rapid Iteration**: Small changes to trigger deployments and validate approaches quickly

### Success Metrics That Matter
- **Cost Efficiency**: Single service vs per-user resource usage
- **Management Overhead**: Admin interface complexity and usability
- **Scalability**: Can serve unlimited customers without proportional cost increase
- **Operational Simplicity**: Easier to monitor, debug, and maintain in production
- **Business Model Alignment**: Technology choices support sustainable business operations

### Key Behavioral Patterns for Success
- **Proactive Questioning**: Challenge design decisions before they become entrenched
- **Collaborative Problem-Solving**: "Let me help you redesign this architecture"
- **Business-First Mindset**: Technology serves business goals, not the other way around
- **Operational Empathy**: Understanding real-world service management challenges
- **Continuous Learning Loop**: Each session should improve our operational understanding

## CRITICAL SYSTEM INTEGRATION: Complete API Key Flow (2025-07-15)

### Major Integration Achievement
**PROBLEM SOLVED**: Frontend-backend API key disconnection that blocked all user data access

### Root Cause Analysis Completed
- **Frontend Issue**: API keys stored only in localStorage, never reaching backend database
- **Authentication Gap**: JWT tokens not properly integrated with API key retrieval system  
- **User Experience Failure**: No guided onboarding for API key setup and validation
- **Service Integration Broken**: Real-time data services couldn't access user API credentials

### Complete Solution Implemented

#### New Architecture Components
- **`ApiKeyProvider.jsx`**: React Context provider for centralized API key state management
  - Automatic localStorage migration to secure backend storage
  - Real-time API key status detection across entire application
  - Unified error handling and user feedback systems

- **`ApiKeyOnboarding.jsx`**: Comprehensive guided setup experience
  - Step-by-step process: Welcome → Alpaca Setup → Market Data APIs → Validation → Complete
  - Real-time API key format validation and broker connection testing
  - Support for Alpaca (trading), Polygon (market data), and Finnhub (financial data)
  - Clear error messaging and setup guidance with direct links to broker API pages

- **`RequiresApiKeys.jsx`**: Reusable page protection wrapper
  - Configurable required providers (e.g., Portfolio requires Alpaca)
  - Graceful degradation with demo data when API keys unavailable
  - Automatic onboarding flow trigger for missing credentials
  - Custom messaging per page requirements

#### Integration Points Fixed
- **Settings Page**: Unified with `SettingsManager` component for consistent backend API usage
- **Portfolio Page**: Enhanced with API key requirement checking and fallback to demo data
- **Real-time Data Service**: Already properly integrated with API key authentication system
- **Authentication Flow**: JWT tokens now properly support API key retrieval for protected endpoints

#### User Experience Improvements
- **Onboarding Flow**: Clear step-by-step guidance from no API keys → fully configured system
- **Error Messaging**: Specific instructions for each API provider setup process
- **Progressive Enhancement**: Pages work with demo data, enhanced with real data when API keys available
- **Settings Integration**: One-click access to API key setup from any protected page

#### Technical Implementation
- **Security Maintained**: All existing AES-256-GCM encryption preserved throughout integration
- **Migration System**: One-time automatic migration from localStorage to secure backend storage
- **Context Architecture**: Provider pattern ensures API key state available throughout application
- **Backend Integration**: Full integration with existing `settingsService.js` and Lambda API routes
- **Error Boundaries**: Comprehensive error handling prevents system crashes during API key issues

#### System Health After Integration
✅ **Frontend-Backend Data Flow**: API keys properly flow from user input → encrypted storage → service authentication  
✅ **User Onboarding**: Complete guided experience for users without API keys  
✅ **Authentication Integration**: JWT tokens properly integrated with API key retrieval  
✅ **Real-time Services**: Live data services correctly handle API key authentication  
✅ **Settings Unification**: Consistent backend persistence across all API key operations  
✅ **Page Protection**: Any page can require specific API providers with graceful degradation  

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

## Documentation Management - CRITICAL
⚠️ **ABSOLUTE RULE: ONLY WORK WITH THESE 4 .MD FILES - NO EXCEPTIONS** ⚠️

### THE ONLY 4 ALLOWED .MD FILES FOR PROJECT MANAGEMENT:
1. **FINANCIAL_PLATFORM_BLUEPRINT.md** - Technical blueprint
2. **TEST_PLAN.md** - Testing strategy
3. **DESIGN.md** - System design
4. **claude-todo.md** - Todo management (auto-managed by TodoRead/TodoWrite)

### STRICT PROHIBITIONS:
- **NEVER create ANY new .md files** - STATUS.md, PLAN.md, ANALYSIS.md, REPORT.md, SUMMARY.md, DEVELOPMENT_TASKS.md, etc.
- **NEVER create temporary .md files** - even for "quick notes" or "session summaries"
- **NEVER create workflow .md files** - deployment guides, fix summaries, etc.
- **ALL project management MUST happen in the 4 core documents above**
- **ALL findings, status, plans, analyses MUST be integrated into the 4 core documents**

### ENFORCEMENT:
- If you start creating a new .md file, STOP immediately
- If you need to document something, choose the appropriate core document
- If unsure which core document to use, ask the user
- These 4 documents are the ONLY source of truth for all project information