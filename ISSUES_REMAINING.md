# All Remaining Issues Found & To-Do

## FIXED THIS SESSION
- [x] Missing database tables (3) - FIXED
- [x] Hardcoded credentials (check_stage2.py) - DELETED
- [x] Bare except statements - FIXED
- [x] Unimplemented functions - FIXED
- [x] CI blocker: credential_manager imports (114+ files) - FIXED

## REMAINING ISSUES

### 1. Test Files That Need Review (45+ files)
- test_algo_system.py — missing pytest/unittest
- test_e2e.py — missing pytest/unittest
- test_base_detection.py — missing pytest/unittest
- Plus 42+ more test files
**Action:** Keep or delete? Most are development artifacts.

### 2. API Endpoints
**Action:** Verify all 30+ endpoints in lambda/api/ exist and match frontend expectations

### 3. Data Loaders (36 loaders)
**Action:** Verify each loader:
- Writes to correct tables
- Column names match schema
- Properly scheduled in EventBridge/Step Functions

### 4. Frontend Pages (30 pages)
**Action:** Verify each page has corresponding API endpoint

### 5. Lambda Package Copies
- lambda-pkg/ is a copy of main code
- db-init-pkg/ is a copy of db-init code
**Action:** Verify they're in sync with main

## PRIORITY ORDER
1. (DONE) Fix CI blocker
2. (NEXT) Verify API endpoints exist and match frontend
3. Verify data loaders work correctly
4. Clean up test files
