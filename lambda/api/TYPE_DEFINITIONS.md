# API Type Definitions & OpenAPI Specification

This document describes the type system for the Algo Trading API, including how to access type definitions and generate client code.

## Quick Start

### Access the OpenAPI Spec

- **JSON Specification**: `/api/openapi.json` - Machine-readable OpenAPI 3.0 spec
- **Swagger UI**: `/api/swagger` - Interactive API documentation and testing
- **ReDoc**: `/api/redoc` - Alternative documentation viewer

All endpoints are public (no authentication required).

### Example: Using the JSON Spec in Frontend

```typescript
// Fetch the OpenAPI spec
const response = await fetch('/api/openapi.json');
const spec = await response.json();

// Use with code generators or type checkers
// See Frontend Type Generation section below
```

## Response Types

All API responses follow a consistent format:

### Success Response (Single Object)

```json
{
  "statusCode": 200,
  "data": {
    "symbol": "AAPL",
    "company_name": "Apple Inc.",
    "sector": "Technology"
  }
}
```

**TypeScript Type**:
```typescript
interface SuccessResponse<T> {
  statusCode: 200;
  data: T;
  data_freshness?: DataFreshness;
}
```

### List Response (Paginated)

```json
{
  "statusCode": 200,
  "data": {
    "items": [
      { "symbol": "AAPL", "signal": "BUY", "date": "2026-06-14T10:30:00Z" },
      { "symbol": "MSFT", "signal": "SELL", "date": "2026-06-14T09:15:00Z" }
    ],
    "total": 150,
    "limit": 50,
    "offset": 0
  },
  "data_freshness": {
    "status": "OK",
    "age_hours": 2.5,
    "warning_threshold_days": 1
  }
}
```

**TypeScript Type**:
```typescript
interface ListResponse<T> {
  statusCode: 200;
  data: {
    items: T[];
    total: number;
    limit?: number;
    offset?: number;
  };
  data_freshness?: DataFreshness;
}
```

### Error Response

```json
{
  "statusCode": 400,
  "errorType": "bad_request",
  "message": "Invalid symbol format",
  "_error": "bad_request"
}
```

**TypeScript Type**:
```typescript
interface ErrorResponse {
  statusCode: number;
  errorType: string;
  message: string;
  _error: string;
  _diagnostic?: Record<string, any>;
}
```

### Data Freshness Metadata

All list responses include optional `data_freshness` metadata:

```json
{
  "status": "OK",
  "table_name": "buy_sell_daily",
  "age_hours": 2.5,
  "age_days": 0.1,
  "last_updated": "2026-06-14T12:30:00Z",
  "warning_threshold_days": 1
}
```

**Freshness Status Values**:
- `OK` - Data is fresh (within normal range)
- `WARNING` - Data is slightly stale (within 7-14 days, depending on endpoint)
- `STALE` - Data is notably stale (>7 days)
- `CRITICAL` - Data is very stale or missing (>14 days)

## Python Type Definitions

All response types are defined using Pydantic v2 models in `models/responses.py`:

### Common Models

```python
from models.responses import (
    # Base types
    SuccessResponse,
    ListResponse,
    ErrorResponse,
    DataFreshness,
    
    # Specific response types
    HealthResponse,
    StockProfileResponse,
    SignalsResponse,
    KeyMetricsResponse,
    IncomeStatementResponse,
    BalanceSheetResponse,
    PriceDataResponse,
)
```

### Using Models in Python

```python
from models.responses import SignalsResponse, Signal
from openapi_spec import generate_openapi_spec

# Validate a response
signal_data = [
    {"symbol": "AAPL", "signal": "BUY", "date": "2026-06-14T10:30:00Z"},
    {"symbol": "MSFT", "signal": "SELL", "date": "2026-06-14T09:15:00Z"},
]

response = SignalsResponse(
    statusCode=200,
    data={
        "items": signal_data,
        "total": len(signal_data)
    }
)

# Export as JSON
json_str = response.model_dump_json()
```

## Frontend Type Generation

### Option 1: Using OpenAPI Generator

Generate TypeScript types from the OpenAPI spec:

```bash
# Install openapi-generator
npm install @openapitools/openapi-generator-cli -g

# Generate TypeScript client
openapi-generator generate \
  -i http://localhost:8000/api/openapi.json \
  -g typescript-fetch \
  -o ./src/generated/api
```

### Option 2: Using swagger-typescript-api

```bash
npm install -D swagger-typescript-api

# Generate types
npx swagger-typescript-api -p http://localhost:8000/api/openapi.json -o ./src/generated
```

### Option 3: Using json-schema-to-typescript

```bash
npm install -D json-schema-to-typescript

# Extract schema and generate types
curl http://localhost:8000/api/openapi.json | \
  jq '.components.schemas' | \
  json2ts --input json -o ./src/generated/types.ts
```

### Generated TypeScript Example

After code generation, you get fully typed API client:

```typescript
import { SignalsResponse, Signal } from './generated/api';

// Fetch signals with type safety
const response: SignalsResponse = await apiClient.getSignals({
  limit: 100,
  timeframe: 'daily'
});

// Types are automatically enforced
response.data.items.forEach((signal: Signal) => {
  console.log(`${signal.symbol}: ${signal.signal}`);
});

// TypeScript compiler prevents incorrect usage
// response.data.items.forEach((item) => {
//   console.log(item.nonexistentField);  // ERROR: Property 'nonexistentField' does not exist
// });
```

## API Endpoint Documentation

### Health Endpoints

#### `GET /api/health`
Basic health check (no auth required)

**Response**:
```json
{
  "statusCode": 200,
  "data": {
    "status": "healthy",
    "version": "v2-2026-06-14",
    "timestamp": "2026-06-14T10:30:00Z",
    "api_route_imports": {
      "status": "healthy",
      "failed_count": 0
    },
    "freshness": {
      "status": "OK",
      "age_hours": 1.5
    }
  }
}
```

### Stock Endpoints

#### `GET /api/stocks/{symbol}`
Get stock profile and company information

**Parameters**:
- `symbol` (path, required): Stock symbol (e.g., `AAPL`, `BRK-A`)

**Response**:
```json
{
  "statusCode": 200,
  "data": {
    "symbol": "AAPL",
    "company_name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "website": "https://www.apple.com",
    "employees": 164000,
    "exchange": "NASDAQ"
  }
}
```

### Signals Endpoints

#### `GET /api/signals`
Get trading signals

**Parameters**:
- `limit` (query, default: 500, max: 10000): Number of signals
- `timeframe` (query, enum: "daily"): Signal timeframe
- `symbol` (query, optional): Filter by stock symbol

**Response**: `ListResponse<Signal>`

**Signal Object Fields**:
- `id`: Signal database ID
- `symbol`: Stock symbol
- `signal`: "BUY" or "SELL"
- `date`: Signal date/time
- `strength`: Signal strength (0-100)
- `signal_quality_score`: Quality score (0-100)
- `rsi`: RSI indicator value
- `sma_50`, `sma_200`: Moving averages
- `sector`, `industry`: Classification
- `_is_fallback`: Whether data includes fallbacks/defaults

### Financial Endpoints

#### `GET /api/financials/{symbol}/key-metrics`
Get key financial metrics

**Parameters**:
- `symbol` (path, required): Stock symbol
- `period` (query, enum: "annual"|"quarterly", default: "annual"): Reporting period

**Response**: `ListResponse<KeyMetrics>`

**Key Metrics Fields**:
- `pe_ratio`: Price-to-earnings
- `price_to_book`: Price-to-book ratio
- `price_to_sales`: Price-to-sales ratio
- `dividend_yield`: Annual dividend yield
- `debt_to_equity`: Debt-to-equity ratio
- `return_on_equity`: ROE percentage
- `return_on_assets`: ROA percentage
- `current_ratio`, `quick_ratio`: Liquidity ratios
- `market_cap`: Market capitalization

## Error Handling

All errors follow the same format with a machine-readable `errorType`:

| HTTP Code | errorType | Meaning |
|-----------|-----------|---------|
| 400 | `bad_request` | Invalid parameters |
| 401 | `unauthorized` | Authentication required |
| 404 | `not_found` | Resource not found |
| 503 | `connection_error` | Database connection failed |
| 503 | `schema_error` | Database migration issue |
| 503 | `query_error` | SQL query execution failed |
| 504 | `timeout` | Request exceeded timeout |
| 500 | `internal_error` | Unexpected server error |

### Error Response Example

```json
{
  "statusCode": 503,
  "errorType": "connection_error",
  "message": "Database connection failed",
  "_error": "connection_error",
  "_diagnostic": {
    "failed_module": "stocks",
    "module_error": "OperationalError: unable to connect",
    "failed_route_count": 2,
    "critical_failures": []
  }
}
```

## API Versioning

- Current version: `v2-2026-06-14`
- Versioning strategy: Breaking changes increment major version
- Version returned in health check: `/api/health`

## Best Practices

### 1. Always Check Status Code
```typescript
const response = await fetch('/api/signals');
const result = await response.json();

if (result.statusCode === 200) {
  // Handle success
  const signals = result.data.items;
} else {
  // Handle error
  console.error(`Error ${result.errorType}: ${result.message}`);
}
```

### 2. Handle Data Freshness Warnings
```typescript
const response: ListResponse<Signal> = await apiClient.getSignals();

if (response.data_freshness?.status === 'STALE') {
  console.warn('Data is stale, consider refreshing');
  ui.showWarning('Trading signals are not up to date');
}
```

### 3. Use Type Guards in TypeScript
```typescript
function isSuccessResponse<T>(response: any): response is SuccessResponse<T> {
  return response.statusCode === 200 && 'data' in response;
}

function isErrorResponse(response: any): response is ErrorResponse {
  return response.statusCode >= 400 && 'errorType' in response;
}

// Usage
if (isSuccessResponse<Signal>(response)) {
  // TypeScript narrows type to SuccessResponse<Signal>
  response.data.items.forEach(signal => {});
} else if (isErrorResponse(response)) {
  // TypeScript narrows type to ErrorResponse
  logError(response.errorType);
}
```

### 4. Implement Retry Logic for Stale Data
```typescript
async function fetchSignalsWithRetry(maxAttempts = 3): Promise<ListResponse<Signal>> {
  for (let i = 0; i < maxAttempts; i++) {
    const response = await fetch('/api/signals');
    const data = await response.json();
    
    if (data.data_freshness?.status !== 'STALE') {
      return data;
    }
    
    if (i < maxAttempts - 1) {
      await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
    }
  }
  
  throw new Error('Unable to fetch fresh data');
}
```

## Schema Reference

See `/api/openapi.json` for complete schema definitions. Key schemas include:

- `SuccessResponse` - Single object response
- `ListResponse` - Paginated list response
- `ErrorResponse` - Error response
- `DataFreshness` - Data freshness metadata
- `Signal` - Trading signal with all technical indicators
- `StockProfile` - Company information
- `KeyMetrics` - Financial metrics
- `IncomeStatement` - Income statement data
- `BalanceSheet` - Balance sheet data
- `PriceData` - OHLCV price data

## Updates & Maintenance

When API changes are made:
1. Update the Pydantic models in `models/responses.py`
2. Update `openapi_spec.py` with new endpoints/schemas
3. Update route handlers to use the models
4. Regenerate frontend types from the new OpenAPI spec
5. Test frontend with new types

The OpenAPI spec is the single source of truth for API contracts. Always consult `/api/openapi.json` for current API structure.
