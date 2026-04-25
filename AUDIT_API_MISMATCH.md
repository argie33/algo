# API ROUTING & RESPONSE MAPPING AUDIT

## Phase 1: Find All Routing Issues
<AUDIT_IN_PROGRESS>

Running comprehensive scan for:
1. Frontend API calls vs actual endpoints
2. Missing routes
3. Wrong paths
4. Typos in endpoint names

## Phase 2: Find All Response Structure Mismatches

Checking:
1. What frontend expects vs what API returns
2. Field name mismatches (e.g., `total_analysts` vs `analyst_count`)
3. Missing fields in API response
4. Extra fields in API response

## Known Issues Found So Far:

### Routing Issues ✅ FIXED
- [x] `/api/sectors/sectors` - Was 404, now aliased ✅
- [x] `/api/industries/industries` - Was 404, now aliased ✅

### Response Mapping Issues (NEED TO AUDIT):
- [ ] Sentiment endpoint - column name mapping
- [ ] Stock scores endpoint - pagination format
- [ ] Financials endpoint - field names
- [ ] Strategies endpoint - field names
- [ ] Portfolio endpoint - field names

## Next: Run diagnostic queries to find mismatches
