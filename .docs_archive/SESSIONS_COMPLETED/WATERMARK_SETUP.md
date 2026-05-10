# Watermark Store Setup & Usage

## Overview

The watermark system enables **incremental data loading** - loading only new data since the last successful run. This reduces API calls by 80-90% and improves performance.

## Architecture

```
Loader starts
    ↓
Get last watermark timestamp from DynamoDB
    ↓
Query API for data since timestamp (instead of all data)
    ↓
Load new data to database
    ↓
Update watermark with new timestamp
    ↓
Mark watermark as "success"
```

## Benefits

| Scenario | Without Watermark | With Watermark |
|----------|-------------------|----------------|
| Daily load (1000 stocks) | 1000 API calls | 50 API calls (only new) |
| Load time | 15 minutes | 2 minutes |
| Database writes | 1000 rows | 50 rows (new only) |
| Failure recovery | Restart from beginning | Resume from last timestamp |
| API rate limits | Hit quickly (50 req/sec) | 1 req/sec average |

## Prerequisites

- DynamoDB table deployed (see Terraform setup below)
- AWS permissions: `dynamodb:GetItem`, `dynamodb:PutItem`
- Python 3.9+

## Terraform Deployment

The watermark DynamoDB table is automatically created by the database module:

```bash
cd terraform

# Deploy database module (includes watermark table)
terraform apply -target=module.database

# Verify table was created
aws dynamodb describe-table \
  --table-name algo-watermarks-prod \
  --query 'Table.[TableName,TableStatus,BillingModeSummary]'
```

Table configuration:
- **Billing**: Pay-per-request (on-demand, ~$0.25/million reads)
- **TTL**: 90 days (auto-deletes stale records)
- **PITR**: Enabled for prod, disabled for dev
- **Destroy Protection**: Enabled for prod

## Usage: Time-Based Watermark

Track last load timestamp (e.g., "loaded data through May 8, 2026"):

```python
from watermark_manager import WatermarkManager
from datetime import datetime

# Initialize watermark for this data source
watermark = WatermarkManager(source="daily_prices")

# Get last successful load time
last_timestamp = watermark.get_last_timestamp()

if last_timestamp:
    # Load only data SINCE last_timestamp
    logger.info(f"Loading data since {last_timestamp}")
    new_data = fetch_data_since(last_timestamp)
else:
    # First run: load full history
    logger.info("First run: loading full historical data")
    new_data = fetch_all_historical_data()

# Load to database
load_to_db(new_data)

# Update watermark on SUCCESS
watermark.set_last_timestamp(datetime.utcnow())
watermark.mark_success(records_loaded=len(new_data))
```

## Usage: ID-Based Watermark

Track last loaded ID (for APIs with cursor-based pagination):

```python
from watermark_manager import WatermarkManager

watermark = WatermarkManager(source="earnings")

# Get last cursor position
last_cursor = watermark.get_last_id()

# Paginated load starting from cursor
cursor = last_cursor
while True:
    page = fetch_earnings(cursor=cursor)
    
    if not page:
        break
    
    # Load page
    load_to_db(page["data"])
    
    # Update cursor for next iteration
    cursor = page.get("next_cursor")
    if not cursor:
        break

# Update watermark with final cursor
watermark.set_last_id(cursor)
watermark.mark_success(records_loaded=page_count)
```

## Usage: Batch Update

Update multiple watermarks together (all succeed or all fail):

```python
from watermark_manager import WatermarkBatch, WatermarkManager

wm_prices = WatermarkManager(source="daily_prices")
wm_earnings = WatermarkManager(source="earnings")

try:
    with WatermarkBatch(wm_prices, wm_earnings) as batch:
        # Load both data sources
        load_prices()
        load_earnings()
        
        # Both watermarks update together on success
        batch.mark_success(records_loaded=5000)

except Exception as e:
    # Both watermarks marked as failed on error
    # (happens automatically on exception)
    logger.error(f"Load failed: {e}")
```

## Integration with OptimizedLoader

Integrate watermark into your custom loader:

```python
from loader_base_optimized import OptimizedLoader
from watermark_manager import WatermarkManager, WatermarkBatch

class MyIncrementalLoader(OptimizedLoader):
    def __init__(self):
        super().__init__()
        self.watermark = WatermarkManager(source="my_data_source")

    def load(self, symbols):
        try:
            with WatermarkBatch(self.watermark):
                # Get last watermark
                last_timestamp = self.watermark.get_last_timestamp()
                
                # Load only new data
                self.connect()
                self.create_tables()
                
                for symbol in symbols:
                    if last_timestamp:
                        rows = self._fetch_since(symbol, last_timestamp)
                    else:
                        rows = self._fetch_all(symbol)
                    
                    for row in rows:
                        self.add_row(row)
                    
                    self.commit_if_needed()
                
                self.finalize()
                
                # Update watermark timestamp
                self.watermark.set_last_timestamp(datetime.utcnow())
                
        finally:
            self.disconnect()
```

See `loader_with_watermark_example.py` for complete example.

## Monitoring Watermarks

### View Watermark Status

```python
from watermark_manager import WatermarkManager

watermark = WatermarkManager(source="daily_prices")
status = watermark.get_status()

print(status)
# {
#     'source': 'daily_prices',
#     'status': 'success',
#     'last_timestamp': '2026-05-09T15:30:45.123456',
#     'last_load_at': '2026-05-09T15:30:45.123456',
#     'records_loaded': 1000,
#     'error': None,
#     'error_count': 0
# }
```

### Query DynamoDB Directly

```bash
# List all watermarks
aws dynamodb scan \
  --table-name algo-watermarks-prod \
  --query 'Items[*].[source, #s, updated_at]' \
  --expression-attribute-names '{"#s":"status"}'

# Get specific watermark
aws dynamodb get-item \
  --table-name algo-watermarks-prod \
  --key '{"source": {"S": "daily_prices"}}'

# Query by status (failed loads)
aws dynamodb query \
  --table-name algo-watermarks-prod \
  --index-name StatusIndex \
  --key-condition-expression '#s = :status' \
  --expression-attribute-names '{"#s":"status"}' \
  --expression-attribute-values '{":status": {"S": "failed"}}'
```

### CloudWatch Monitoring

Stale data alarm: alerts if no updates in 2+ hours

```bash
# Check alarm status
aws cloudwatch describe-alarms \
  --alarm-names algo-watermark-stale-prod
```

## Testing Watermarks Locally

Use local file backend (no AWS required):

```bash
# Set backend to local file storage
export WATERMARK_DIR=./.watermarks

# Run loader - creates .watermarks/source_name.json locally
python my_loader.py

# Inspect watermark file
cat .watermarks/daily_prices.json
```

## Maintenance

### Reset Watermark (Full Reload)

To reload all data (e.g., data correction):

```python
watermark = WatermarkManager(source="daily_prices")
watermark.clear()  # Delete watermark

# Next run will load full history
```

Or via CLI:

```bash
aws dynamodb delete-item \
  --table-name algo-watermarks-prod \
  --key '{"source": {"S": "daily_prices"}}'
```

### Manual Watermark Update

Reset to specific date:

```python
from datetime import datetime

watermark = WatermarkManager(source="daily_prices")
watermark.set_last_timestamp(datetime(2026, 1, 1))

# Next load will start from Jan 1, 2026
```

### View Error History

```bash
aws dynamodb query \
  --table-name algo-watermarks-prod \
  --index-name StatusIndex \
  --key-condition-expression '#s = :status' \
  --expression-attribute-names '{"#s":"status"}' \
  --expression-attribute-values '{":status": {"S": "failed"}}' \
  --projection-expression 'source,#e,#ec,#da' \
  --expression-attribute-names '{
    "#s": "status",
    "#e": "error",
    "#ec": "error_count",
    "#da": "last_error_at"
  }'
```

## Troubleshooting

### "Table not found" Error

DynamoDB table not created yet:

```bash
# Deploy table
terraform apply -target=module.database

# Verify
aws dynamodb list-tables | grep watermark
```

### "Access Denied" Error

Lambda/loader doesn't have DynamoDB permissions:

```bash
# Attach watermark policy to loader IAM role
aws iam attach-role-policy \
  --role-name algo-loader-role \
  --policy-arn arn:aws:iam::ACCOUNT:policy/algo-watermark-access-prod
```

### Watermark Not Updating

Check if `mark_success()` is being called:

```python
# Add logging
watermark.mark_success(records_loaded=100)  # Should log "Marked as success"

# Verify in CloudWatch
aws logs tail /aws/lambda/my-loader --follow
```

### Stale Watermark Alarm

Alert fired: watermark hasn't been updated in 2 hours:

1. Check loader logs: is it running?
2. Check DynamoDB metrics: any write errors?
3. Check RDS: is database accepting writes?
4. Manually trigger loader: `aws lambda invoke ...`

## Cost

DynamoDB watermark table costs ~$0.25/million reads (on-demand pricing):

- Each load: 1 read + 1 write = ~$0.0000004
- 100 loaders/day = $0.00004/day
- Annual cost: ~$0.01

Negligible compared to API savings (80-90% fewer calls).

## References

- Code: `watermark_manager.py`
- Example: `loader_with_watermark_example.py`
- DynamoDB Docs: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/
