# Test Strategy & Coverage Plan

## Test Architecture

Our tests are organized into three layers with clear boundaries:

### **Unit Tests** - Individual Component/Function Testing
**Location**: `tests/unit/`
**Purpose**: Test individual functions, services, and isolated components
**Mocking**: Mock all external dependencies
**Focus**: Business logic, utility functions, service methods

**Key Files**:
- `apiKeyService.unit.test.js` - Service logic, encryption, JWT validation
- `database.unit.test.js` - Database utilities, connection pooling
- `logger.unit.test.js` - Logging functionality
- `responseFormatter.test.js` - Response formatting utilities

### **Integration Tests** - Component Interaction Testing
**Location**: `tests/integration/` and `tests/unit/routes/`
**Purpose**: Test component interactions, API contracts, data flow
**Mocking**: Minimal mocking, test real integrations
**Focus**: API endpoints, database interactions, service coordination

**Key Files**:
- `settings.test.js` - Settings API endpoint integration
- `portfolio.test.js` - Portfolio API route integration
- `health.api.test.js` - Health check endpoint integration

### **Component Tests** - UI Component Behavior
**Location**: `tests/unit/components/`
**Purpose**: Test React component behavior, user interactions, state management
**Mocking**: Mock external services, test component integration
**Focus**: UI behavior, user interactions, prop handling, state changes

**Key Files**:
- `ApiKeysTab.test.jsx` - API key management UI
- `Portfolio.test.jsx` - Portfolio display component
- `Dashboard.test.jsx` - Dashboard component behavior

## Test Coverage Goals

### **Unit Tests Coverage**
- ✅ API Key Service (JWT, encryption, validation)
- ✅ Database utilities (connection, pooling, health)
- ✅ Authentication middleware
- ✅ Response formatting
- ✅ Error handling utilities
- ✅ Logging service

### **Integration Tests Coverage**  
- ✅ Settings API endpoints (CRUD operations)
- ✅ Portfolio API routes (VaR calculations, health)
- ✅ Authentication flows (token validation)
- ✅ Database integration (query execution)
- ⚠️ **NEEDED**: End-to-end user workflows
- ⚠️ **NEEDED**: Live data service integration

### **Component Tests Coverage**
- ✅ API Keys UI (authentication, CRUD operations)
- ✅ Portfolio display (data rendering, error states)
- ✅ Dashboard components (widget interactions)
- ⚠️ **NEEDED**: Authentication modal flows
- ⚠️ **NEEDED**: Error boundary testing
- ⚠️ **NEEDED**: Real-time data components

## Eliminated Duplicates

### **Before Consolidation**:
- API key testing duplicated across 3 files with overlapping coverage
- Portfolio testing duplicated between lambda and api directories
- Component tests testing API integration instead of UI behavior

### **After Consolidation**:
- **Unit Tests**: Focus on service logic only
- **Integration Tests**: Focus on API contracts and data flow
- **Component Tests**: Focus on UI behavior and user interactions

## Missing Coverage - Priority List

### **Critical Missing Tests**:
1. **End-to-End User Workflows** 
   - User registration → API key setup → portfolio view
   - Error scenarios and recovery paths

2. **Database Integration Tests**
   - Real database queries with test data
   - Connection pooling under load
   - Transaction handling

3. **Authentication Flow Integration**
   - JWT token refresh
   - Session expiration handling
   - Multi-device login scenarios

4. **Real-time Data Integration**
   - WebSocket connection handling
   - Live data service integration
   - Data synchronization tests

### **Recommended Test Files to Create**:
- `tests/e2e/user-workflows.test.js` - Complete user journeys
- `tests/integration/database-integration.test.js` - Real DB operations
- `tests/integration/auth-flow.test.js` - Authentication scenarios
- `tests/integration/live-data.test.js` - Real-time data testing

## Test Execution Strategy

### **Development Workflow**:
1. **Unit Tests First** - Run on every code change
2. **Integration Tests** - Run before commits
3. **Component Tests** - Run with UI changes
4. **E2E Tests** - Run before releases

### **CI/CD Integration**:
- **Pull Requests**: All unit + integration tests
- **Staging Deploys**: Full test suite including E2E
- **Production Deploys**: Smoke tests + critical path validation

## Test Quality Standards

### **Code Coverage Targets**:
- Unit Tests: 90%+ coverage of business logic
- Integration Tests: 100% coverage of API endpoints
- Component Tests: 85%+ coverage of UI components

### **Performance Targets**:
- Unit Tests: <5 seconds total execution
- Integration Tests: <30 seconds total execution
- Component Tests: <20 seconds total execution
- E2E Tests: <2 minutes critical path

### **Quality Gates**:
- All tests must pass before merge
- No test should be flaky (>95% pass rate)
- Tests must be maintainable and readable
- Mock data must reflect real data structures