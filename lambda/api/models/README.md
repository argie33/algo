# API Response Models

Pydantic v2 models for all API response types. These models serve as the single source of truth for API contracts.

## Quick Reference

### Base Types

```python
from models.responses import (
    BaseResponse,        # Base class for all responses
    SuccessResponse,     # Success response (single object)
    ListResponse,        # Success response (paginated list)
    ListResponseData,    # Container for list data
    ErrorResponse,       # Error response
    DataFreshness,       # Data freshness metadata
)
```

### Response Types by Endpoint

```python
# Health checks
from models.responses import HealthResponse

# Stock data
from models.responses import StockProfileResponse, StockScoresResponse

# Signals
from models.responses import SignalsResponse, Signal

# Financial data
from models.responses import (
    KeyMetricsResponse,
    IncomeStatementResponse,
    BalanceSheetResponse,
    PriceDataResponse,
)

# Market data
from models.responses import (
    SectorResponse,
    IndustryResponse,
    EconomicResponse,
    EarningsResponse,
)

# Trading
from models.responses import TradesResponse

# Other
from models.responses import (
    SearchResponse,
    ContactResponse,
    SettingsResponse,
    DataCoverageResponse,
)
```

## Usage Examples

### Validating a Response

```python
from models.responses import SignalsResponse
import json

# Fetch from API
response_json = '''
{
  "statusCode": 200,
  "data": {
    "items": [
      {"symbol": "AAPL", "signal": "BUY", "date": "2026-06-14T10:30:00Z"}
    ],
    "total": 1
  }
}
'''

# Validate with Pydantic
response = SignalsResponse.model_validate_json(response_json)
print(f"Status: {response.statusCode}")
print(f"Signals: {len(response.data.items)}")
```

### Creating a Response

```python
from models.responses import (
    SuccessResponse,
    StockProfile,
)

# Create a response
profile = StockProfile(
    symbol="AAPL",
    company_name="Apple Inc.",
    sector="Technology",
)

response = SuccessResponse(
    statusCode=200,
    data=profile.model_dump()
)

# Convert to JSON
json_str = response.model_dump_json(by_alias=True)
```

### Accessing Response Data

```python
from models.responses import SignalsResponse
from models.responses import Signal

response = SignalsResponse(...)

# Access list items
for item in response.data.items:
    print(f"{item['symbol']}: {item['signal']}")

# Access metadata
print(f"Total: {response.data.total}")
print(f"Limit: {response.data.limit}")
print(f"Offset: {response.data.offset}")

# Access freshness info
if response.data_freshness:
    print(f"Data status: {response.data_freshness.status}")
    print(f"Age: {response.data_freshness.age_hours} hours")
```

### Error Handling

```python
from models.responses import ErrorResponse

try:
    response = ErrorResponse.model_validate({
        "statusCode": 400,
        "errorType": "bad_request",
        "message": "Invalid symbol format",
        "_error": "bad_request"
    })
    print(f"Error type: {response.errorType}")
    print(f"Message: {response.message}")
except ValueError as e:
    print(f"Invalid response: {e}")
```

## Field Aliases

Some fields use Python naming conventions but are returned with underscores in JSON:

```python
# Python attribute name -> JSON field name
error          -> _error
diagnostic     -> _diagnostic
is_fallback    -> _is_fallback
```

When converting to JSON, use `by_alias=True`:

```python
response = ErrorResponse(...)
json_str = response.model_dump_json(by_alias=True)
# Output: {"statusCode": ..., "_error": ...}
```

## Extending Models

### Adding a New Endpoint Response

1. Define the data model:
```python
from pydantic import BaseModel, Field
from typing import Optional

class CustomData(BaseModel):
    """Custom endpoint response data."""
    field1: str
    field2: Optional[int] = None
    internal_flag: bool = Field(alias="_internal_flag")
```

2. Create a response type:
```python
from models.responses import SuccessResponse

class CustomResponse(SuccessResponse):
    """Response for custom endpoint."""
    data: CustomData
```

3. Export in `__init__.py`:
```python
from .responses import CustomResponse
__all__ = [..., "CustomResponse"]
```

4. Use in route handler:
```python
from models.responses import CustomResponse

def handle(cur, path, method, params, body=None, jwt_claims=None):
    data = CustomData(field1="value", field2=42)
    response = CustomResponse(
        statusCode=200,
        data=data
    )
    return response.model_dump(by_alias=True)
```

### Adding Optional Metadata

All responses can include optional `data_freshness`:

```python
from models.responses import ListResponse, DataFreshness

response = ListResponse(
    statusCode=200,
    data={"items": [...], "total": 10},
    data_freshness=DataFreshness(
        status="OK",
        table_name="signals",
        age_hours=2.5,
        warning_threshold_days=1
    )
)
```

## Validation Rules

### Field Constraints

- `statusCode`: Required, must be valid HTTP status
- `errorType`: Required for error responses, ignored for success
- `message`: Required for error responses
- `_error`: Required for error responses (alias of `error`)
- `data`: Required for success responses
- `data_freshness`: Optional, defaults to None

### Field Types

- Dates: ISO 8601 format (`datetime` objects auto-converted)
- Numbers: `float` or `int` as appropriate
- Lists: Always `items` field in `ListResponseData`
- Objects: `Dict[str, Any]` for flexible structures

### Model Configuration

All models use Pydantic v2 defaults:

```python
class Config:
    # Allow extra fields from database queries
    extra = "allow"

    # Serialize aliases in output
    by_alias = True

    # Use field definitions for schema
    json_schema_extra = {...}
```

## Type Hints for API Handlers

When writing API route handlers, use these type hints:

```python
from typing import Dict, Optional
from models.responses import SuccessResponse, ListResponse, ErrorResponse

def handle(
    cur,
    path: str,
    method: str,
    params: Dict,
    body: Optional[Dict] = None,
    jwt_claims: Optional[Dict] = None
) -> Dict:
    """
    Returns:
        dict: Serialized response (use model_dump(by_alias=True))
    """
    try:
        # Fetch data
        data = fetch_data()

        # Create response
        response = SuccessResponse(
            statusCode=200,
            data={"result": data}
        )

        # Return serialized (routes expect dict, not model)
        return response.model_dump(by_alias=True)

    except Exception as e:
        # Error response
        response = ErrorResponse(
            statusCode=500,
            errorType="internal_error",
            message="Failed to fetch data",
            error="internal_error"  # alias for _error
        )
        return response.model_dump(by_alias=True)
```

## OpenAPI Schema Generation

Models are used to generate OpenAPI schemas via `openapi_spec.py`. When you update models:

1. The OpenAPI spec is automatically regenerated
2. Schema is available at `/api/openapi.json`
3. Frontend can regenerate types from new spec

No manual schema updates needed — keep models as single source of truth.

## Testing

```python
import pytest
from models.responses import SignalsResponse, Signal

def test_signals_response():
    """Test signal response model."""
    response = SignalsResponse(
        statusCode=200,
        data={
            "items": [
                {
                    "id": 1,
                    "symbol": "AAPL",
                    "signal": "BUY",
                    "date": "2026-06-14T10:30:00Z",
                    "strength": 85.5,
                }
            ],
            "total": 1,
        }
    )

    assert response.statusCode == 200
    assert len(response.data.items) == 1
    assert response.data.items[0]["symbol"] == "AAPL"
    assert response.data.total == 1


def test_error_response():
    """Test error response model."""
    from models.responses import ErrorResponse

    response = ErrorResponse(
        statusCode=400,
        errorType="bad_request",
        message="Invalid input",
        error="bad_request"  # alias for _error
    )

    assert response.statusCode == 400
    assert response.errorType == "bad_request"

    # Verify _error is used in JSON
    json_dict = response.model_dump(by_alias=True)
    assert "_error" in json_dict
    assert "_error" not in {"error"}
```

## References

- **Pydantic Docs**: https://docs.pydantic.dev/
- **OpenAPI Spec**: `/api/openapi.json`
- **API Docs**: `/api/swagger` or `/api/redoc`
- **Type Definitions Guide**: See `TYPE_DEFINITIONS.md`
