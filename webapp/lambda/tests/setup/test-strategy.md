# Industry Standard Testing Strategy

## Test Pyramid Implementation

### 1. Unit Tests (70-80%)
- **Location**: `tests/unit/`
- **Purpose**: Test individual functions/components in isolation
- **Dependencies**: Mocked (Jest mocks, test doubles)
- **Database**: In-memory or mocked
- **Speed**: < 5 minutes total
- **CI/CD**: Run on every commit

### 2. Integration Tests (15-20%)
- **Location**: `tests/integration/`
- **Purpose**: Test component interactions with real services
- **Dependencies**: Real AWS services (RDS, Secrets Manager)
- **Database**: Real RDS instance (test environment)
- **Speed**: < 15 minutes total
- **CI/CD**: Run on PR merge, nightly

### 3. E2E Tests (5-10%)
- **Location**: `tests/e2e/`
- **Purpose**: Test complete user workflows
- **Dependencies**: Full AWS stack + external APIs
- **Database**: Production-like RDS
- **Speed**: < 30 minutes total
- **CI/CD**: Run on releases, scheduled

## Infrastructure as Code (IaC)

### Unit Tests
```yaml
# No AWS infrastructure needed
services:
  postgres:
    image: postgres:13
    environment:
      POSTGRES_DB: test_db
```

### Integration Tests
```yaml
# AWS CloudFormation for test environment
Resources:
  TestRDSInstance:
    Type: AWS::RDS::DBInstance
    DeletionPolicy: Delete  # Auto-cleanup
```

### E2E Tests
```yaml
# Full AWS stack deployment
# Production-like but isolated
```