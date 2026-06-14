# Dashboard-API Decoupling Implementation

## Status: Phase 1-2 Complete, Phase 3-4 In Progress

This document tracks the implementation of dashboard-API decoupling to fix the loose coupling issues identified in Issue #19.

### PROBLEM STATEMENT (Issue #19)

Dashboard was tightly coupled to API with:
- Hardcoded API URLs (25+ endpoints with URLs duplicated in fetchers.py)
- Separate validation logic (dashboard's validation ≠ API validation)
- No shared endpoint definitions (changes to API required coordinated updates in multiple files)
- Panel system required modifying dashboard.py, fetchers.py, and panels.py to add new panels
- Dashboard would get out of sync with API changes

### SOLUTION: Shared Contract System

Create a single source of truth for all dashboard-API integration:
- `shared_contracts/dashboard_api_contract.py` - All endpoint definitions, schemas, panels
- `shared_contracts/response_validator.py` - Shared validation logic
- `tools/dashboard/panel_registry.py` - Pluggable panel system

## COMPLETED PHASES

### Phase 1: Shared Contract Layer ✅

**Files Created:**
- `shared_contracts/__init__.py` - Package exports
- `shared_contracts/dashboard_api_contract.py` - Endpoint definitions (24 endpoints)
- `shared_contracts/response_validator.py` - Response validation

**What This Fixes:**
- ✅ Single source of truth for all endpoint paths
- ✅ Schema definitions for each endpoint
- ✅ Data freshness requirements
- ✅ Strict field definitions (fail-fast on missing critical data)
- ✅ Panel definitions with dependencies
- ✅ Endpoint and Panel registries for dynamic lookups

**Key Features:**
```python
# Endpoints defined once, used by both API and dashboard
DASHBOARD_ENDPOINTS = {
    "run": {
        "path": "/api/algo/last-run",
        "response_schema": ResponseSchema(...),
        "freshness_max_age_seconds": 3600,
        "strict_fields": ["run_id", "success"],
        "critical": True,
    },
    # ... 23 more endpoints
}

# Registries for dynamic lookups
EndpointRegistry.get_endpoint_path("run")  # → "/api/algo/last-run"
EndpointRegistry.get_critical_endpoints()  # → Only critical ones
```

### Phase 2: Refactored Fetchers ✅

**Files Updated:**
- `tools/dashboard/fetchers.py` - Updated all 24+ fetchers

**What Changed:**
- ✅ Removed hardcoded URL strings (25+ instances)
- ✅ All fetchers now use `_get_endpoint_path(fetcher_name)` to look up endpoints
- ✅ Updated `FETCHER_METADATA` to be built from shared contract at runtime
- ✅ Fixed response data extraction to use `data.get('data', data)` for consistency

**Migration Example:**
```python
# BEFORE (hardcoded URL)
def fetch_run(c):
    data = api_call('/api/algo/last-run')
    return data

# AFTER (contract-based)
def fetch_run(c):
    endpoint = _get_endpoint_path("run")  # Looks up in DASHBOARD_ENDPOINTS
    data = api_call(endpoint)
    return data.get('data', data)  # Consistent extraction
```

**Benefits:**
- Single place to change endpoint paths (contract)
- Fetchers automatically use contract changes
- Easier to add new endpoints (just add to contract)

## IN-PROGRESS PHASES

### Phase 3: Panel Registry System (60% complete)

**Files Created:**
- `tools/dashboard/panel_registry.py` - Pluggable panel system

**What This Fixes:**
- ✅ Panel registry mechanism created
- ✅ Panel definitions with endpoint dependencies
- ✅ Validation that panels have required endpoints
- ⏳ Still need to update panels.py to use decorator registration
- ⏳ Still need to update dashboard.py to use registry for rendering

**Next Steps for Phase 3:**
1. Update `tools/dashboard/panels.py` to register panels with decorators:
   ```python
   @register_panel("header", endpoint_deps=["mkt", "sentiment"])
   def panel_header_market(data, ...):
       ...
   ```

2. Update `tools/dashboard/dashboard.py` to use registry:
   ```python
   # BEFORE: Explicit imports
   from panels import panel_header_market, panel_portfolio, panel_circuit, ...

   # AFTER: Registry-based
   from panel_registry import get_panel_registry
   registry = get_panel_registry()
   for panel_name in registry.get_panel_names():
       panel_def = registry.get_panel(panel_name)
       if panel_def.can_render(data):
           layout = panel_def.render_function(data)
   ```

### Phase 4: Response Validation Integration (0% complete)

**What This Adds:**
- API route handlers validate responses against contract schemas
- Dashboard validation uses shared ResponseValidator
- Breaking API changes caught automatically

**Files to Update:**
- `lambda/api/routes/algo.py` - Add schema validation
- Import `ResponseValidator` from shared_contracts

## TESTING REQUIRED

### Unit Tests
- [ ] EndpointRegistry lookups
- [ ] PanelRegistry registrations and dependencies
- [ ] ResponseValidator with sample responses
- [ ] Contract consistency (no orphaned endpoints)

### Integration Tests
- [ ] Dashboard fetches from all endpoints via contract
- [ ] Panel registry can find all panels
- [ ] Dashboard renders with missing optional panels
- [ ] Dashboard fails gracefully for missing critical panels

### Compatibility Tests
- [ ] Local dashboard still works (`-local` mode)
- [ ] AWS dashboard still works (with credentials)
- [ ] All 24+ endpoints still return expected data
- [ ] Response structures match contract definitions

## FILES CHANGED

### New Files (Created)
```
shared_contracts/
├── __init__.py
├── dashboard_api_contract.py  (532 lines)
└── response_validator.py       (180 lines)

tools/dashboard/
└── panel_registry.py           (355 lines)

DECOUPLING_IMPLEMENTATION.md    (this file)
```

### Modified Files
```
tools/dashboard/
└── fetchers.py
    - Added: `from shared_contracts import ...`
    - Added: `_get_endpoint_path()` helper
    - Updated: All 24+ fetchers to use contract
    - Changed: FETCHER_METADATA now built at runtime from contract
```

## MIGRATION PATH

The implementation maintains backward compatibility:

1. **Phase 1-2 Complete**: Dashboard and API can run without changes
   - Fetchers use contract but still work the same way
   - No breaking changes to panel rendering

2. **Phase 3**: Dashboard uses panel registry (in progress)
   - Panels self-register instead of being imported explicitly
   - Allows new panels without modifying dashboard.py

3. **Phase 4**: API validates against contract
   - API responses validated against schemas
   - Breaking changes caught at API layer

## WHAT THIS ENABLES

### Before (Tight Coupling)
- Adding new endpoint required:
  1. Implement API route
  2. Add hardcoded URL to fetchers.py
  3. Add FETCHER_METADATA entry
  4. Write fetcher function
  5. Add panel rendering code
  6. Update dashboard.py imports
  7. **6+ files modified, high coordination needed**

### After (Loose Coupling)
- Adding new endpoint requires:
  1. Implement API route
  2. Add definition to `DASHBOARD_ENDPOINTS` in contract
  3. Write fetcher (automatically uses contract URL)
  4. Write panel function (auto-registers via decorator)
  5. **2-3 files modified, can work in parallel**

## OUTSTANDING WORK

### Must-Do (Complete Phase 3-4)
- [ ] Register all existing panels with decorators
- [ ] Update dashboard.py to use panel registry
- [ ] Add response validation to API routes
- [ ] Test full integration with local and AWS dashboards

### Should-Do (Code Quality)
- [ ] Add unit tests for contract and registry
- [ ] Add contract validation script (pre-commit hook)
- [ ] Update OpenAPI spec generator to use contract
- [ ] Document contract maintenance procedures

### Nice-To-Have (Future)
- [ ] Contract validation in CI/CD pipeline
- [ ] Auto-generate API documentation from contract
- [ ] Dashboard auto-discovery of available endpoints
- [ ] Contract versioning for API evolution

## VALIDATION CHECKLIST

Before marking as complete:
- [ ] Dashboard starts without errors
- [ ] All 24+ endpoints fetch data correctly
- [ ] Panel registry can find all panels
- [ ] New endpoints added to contract are automatically used
- [ ] Contract changes don't require code changes in fetchers
- [ ] Response validation catches schema mismatches
- [ ] Tests pass (unit, integration, compatibility)

## MAINTENANCE GUIDELINES

### Adding a New Endpoint
1. Define in `shared_contracts/dashboard_api_contract.py`:
   ```python
   DASHBOARD_ENDPOINTS["new_endpoint"] = {
       "path": "/api/new-endpoint",
       "response_schema": ResponseSchema(...),
       "freshness_max_age_seconds": 3600,
       "strict_fields": ["required_field"],
       "critical": False,
   }
   ```
2. Add fetcher in `tools/dashboard/fetchers.py` (auto-uses contract URL)
3. Optional: Add panel if needed (auto-registers via decorator)

### Adding a New Panel
1. Write panel function with decorator:
   ```python
   @register_panel("new_panel", endpoint_deps=["endpoint1", "endpoint2"])
   def panel_new_panel(data, ...):
       ...
   ```
2. Panel auto-registers and appears in dashboard

### Changing an Endpoint
1. Update definition in contract only
2. Dashboard fetcher automatically uses new URL/schema
3. All code using contract picks up changes

## REFERENCES

- Issue #19: Dashboard Loose Coupling to API
- CLAUDE.md: Steering principles and documentation guidelines
- steering/algo.md: System architecture documentation
