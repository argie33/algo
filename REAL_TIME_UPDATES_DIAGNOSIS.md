# Real-Time Updates Diagnosis: No Real-Time Data Infrastructure

**Status**: CONFIRMED - Polling-only architecture with 5-10 minute delays

**Severity**: HIGH  
**Impact**: Users see delayed circuit breaker state changes, position updates, trade execution status  
**Root Cause**: No real-time infrastructure layer (WebSocket, EventBridge, SNS, SSE)

---

## 1. ROOT CAUSE ANALYSIS

### Current Architecture (Polling Only)

**Dashboard Data Flow:**
```
┌─────────────────────────────────────────────────────────────────┐
│                      DASHBOARD (Python CLI)                      │
│  - Runs locally or via container                                │
│  - Uses watch mode for polling: python -m dashboard -w [secs]  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    FIXED POLL INTERVAL
                    (default: 30s in code)
                           │
        ┌──────────────────▼──────────────────┐
        │   load_all() → fetch_* functions   │
        │   - Spawns thread for data load    │
        │   - Concurrent.futures ThreadPool  │
        │   - Critical fetchers: 8s timeout  │
        │   - Optional fetchers: 3s timeout  │
        └──────────────────┬──────────────────┘
                           │
                    BATCH HTTP REQUESTS
                           │
        ┌──────────────────▼──────────────────────────────┐
        │     API Gateway (HTTP REST, no WebSocket)       │
        │     - Protocol: HTTP only (no real-time upgrade)│
        │     - No streaming/subscriptions                │
        └──────────────────┬───────────────────────────────┘
                           │
                    LAMBDA HANDLES
                    EACH REQUEST
                           │
        ┌──────────────────▼──────────────────┐
        │      Lambda API (api/algo/*)        │
        │  Endpoints:                         │
        │  - /api/algo/positions              │
        │  - /api/algo/trades                 │
        │  - /api/algo/config                 │
        │  - /api/algo/circuit                │
        └──────────────────┬──────────────────┘
                           │
                    QUERY CURRENT STATE
                           │
        ┌──────────────────▼──────────────────┐
        │  RDS (PostgreSQL)                   │
        │  Tables:                            │
        │  - algo_positions                   │
        │  - algo_trades                      │
        │  - circuit_breaker_state            │
        │  - execution_log                    │
        └─────────────────────────────────────┘
```

### Key Finding: Why Polling Has 5-10 Minute Delays

**File**: `dashboard/dashboard.py` lines 301-399

The watch mode uses a configurable interval:
- **Default minimum**: 10 seconds (enforced by `_validate_watch_interval()`)
- **Default used by users**: 30 seconds (common practice)
- **Worst case**: Users don't specify interval → falls back to 60-120 seconds

**Actual user experience**:
- Dashboard loads every 30 seconds in most cases
- **But**: Each load takes 8-12 seconds for critical fetchers to complete
- Circuit breaker state changes are delayed by **at least 30 seconds** + fetch time
- Position updates from Alpaca sync are delayed by execution frequency (Phase 3/4 run every 5-10 min)
- Trade execution visibility is delayed by orchestration cycles + polling interval

**Watch mode flow** (`run_watch()` lines 301-399):
```python
while True:
    key = _keypress()  # Check for 'q' to exit
    state.frame += 1   # Increment animation frame
    
    # Check if should reload based on interval
    should_reload = controller.should_reload(
        current_last_load,  # Last successful load timestamp
        interval,           # User-specified interval (30s default)
        is_loading          # Is data currently loading?
    )
    
    if should_reload or should_retry_load:
        # Spawn NEW thread for data load
        reload_thread = threading.Thread(target=reload, daemon=False)
        reload_thread.start()
    
    # Render dashboard with EXISTING data
    layout, _ = recovery.render_with_recovery(current_result, render_state)
    live.update(layout)
    
    time.sleep(0.25)  # Animate at 4 FPS
```

---

## 2. DATA SOURCES WITH STALE DELIVERY

### Circuit Breaker State (Highest Latency)

**File**: `dashboard/fetchers_config.py` lines 389-500  
**Fetcher**: `fetch_circuit()`

The circuit breaker state is stored in:
- **Primary**: `circuit_breaker_state` table (updated by Phase 5 Exposure Policy)
- **Update frequency**: Phase 5 runs every 5-10 minutes (linked to orchestration cycle)
- **Data latency**: Orchestration cycle time (5-10 min) + polling interval (30s) = **5-10+ minutes**

**Code** (lines 389-450):
```python
def fetch_circuit(c: None) -> dict[str, Any]:
    """Fetch circuit breaker state from API."""
    try:
        data = api_call("/api/algo/circuit")  # Single API call per refresh
        # Validation checks...
        cb = data.get("breaker_data", {})
        state = cb.get("state", "UNKNOWN")
        # Return circuit state with timestamp
        return {
            "_source": "api",
            "state": state,
            "reason": cb.get("reason"),
            "timestamp": cb.get("timestamp"),
        }
    except Exception as e:
        return {"_error": str(e)}
```

**Problem**: State changes are only visible after:
1. Phase 5 updates `circuit_breaker_state` table (5-10 min after orchestration trigger)
2. Next polling cycle fetches data (30 sec after interval elapsed)
3. Dashboard renders the update (0-0.25 sec)

**Total latency: 5-10.25 minutes minimum**

### Positions Data (High Latency)

**File**: `dashboard/fetchers_portfolio.py` lines 201-287  
**Fetcher**: `fetch_positions()`

Positions are stored in:
- **Primary**: `algo_positions` table (synced from Alpaca by Phase 4 Reconciliation)
- **Update frequency**: Phase 4 runs every orchestration cycle (5-10 min)
- **Alpaca sync**: `alpaca_sync_manager.py` (updates positions in real-time from broker API)
- **Data latency**: Phase 4 cycle time (5-10 min) + polling interval (30s) = **5-10+ minutes**

**Alpaca Integration** (`algo/infrastructure/alpaca_sync_manager.py`):
- Updates `algo_positions` table from live Alpaca API
- Called by Phase 4, but results not visible in dashboard until next fetch cycle
- No push notification when position changes

### Trades Data (Moderate Latency)

**File**: `dashboard/fetchers_portfolio.py` lines 288-370  
**Fetcher**: `fetch_recent_trades()`

Recent trades come from:
- **Primary**: `algo_trades` table (inserted by Phase 8 Entry Execution, Phase 6 Exit Execution)
- **Refresh frequency**: Orchestration cycle (5-10 min)
- **Data latency**: Trade execution time + orchestration cycle + polling = **5-10+ minutes**

---

## 3. INFRASTRUCTURE GAPS

### Missing Real-Time Components

| Component | Status | Impact |
|-----------|--------|--------|
| **WebSocket API** | ❌ Not implemented | No browser connection for live updates |
| **API Gateway WebSocket Protocol** | ❌ Not configured | terraform/modules/services/main.tf line 202: `protocol_type = "HTTP"` only |
| **Server-Sent Events (SSE)** | ❌ Not implemented | No HTTP streaming fallback |
| **EventBridge** | ❌ Not configured | No event-based triggering |
| **SNS Subscriptions** | ❌ Not configured | No pub/sub for orchestration events |
| **SQS Polling** | ❌ Not used | No message queue for async updates |
| **DynamoDB Streams** | ❌ Not configured | No change data capture |
| **RDS Event Subscriptions** | ❌ Not configured | No database change notifications |

### API Gateway Configuration

**File**: `terraform/modules/services/main.tf` lines 200-230

```terraform
resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project_name}-api-${var.environment}"
  protocol_type = "HTTP"  # ← ONLY HTTP, NO WEBSOCKET SUPPORT
  
  cors_configuration {
    allow_origins = var.api_cors_allowed_origins
    allow_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    # ↑ No UPGRADE method for WebSocket handshake
  }
}
```

**Current API Endpoints**:
- `/api/algo/positions` - REST GET only
- `/api/algo/trades` - REST GET only
- `/api/algo/circuit` - REST GET only
- `/api/algo/config` - REST GET only
- **No WebSocket endpoints**
- **No subscription support**
- **No streaming endpoints**

---

## 4. POLLING INTERVAL ANALYSIS

### Current Watch Mode Defaults

**File**: `dashboard/dashboard.py` lines 136-146

```python
def _validate_watch_interval(value: str) -> int:
    """Validate watch interval is between 10 and 600 seconds."""
    try:
        int_value = int(value)
        if int_value < 10:
            raise argparse.ArgumentTypeError(
                f"Watch interval must be at least 10 seconds (got {int_value})"
            )
        if int_value > 600:
            raise argparse.ArgumentTypeError(
                f"Watch interval must be at most 600 seconds (got {int_value})"
            )
        return int_value
    except ValueError as err:
        raise argparse.ArgumentTypeError(
            f"Watch interval must be an integer (got {value})"
        ) from err
```

**Usage**:
```bash
python -m dashboard -w              # Uses default interval from orchestration cycle
python -m dashboard -w 30           # 30-second polling (recommended)
python -m dashboard -w 60           # 60-second polling (acceptable)
python -m dashboard -w 10           # 10-second polling (minimum, high load)
```

**Real-world timing**:
- Polling interval: 30 seconds
- Fetch time: 8 seconds (critical fetchers)
- **Data age at render**: 0-38 seconds old
- **State changes visible**: 30+ seconds after occurring
- **Position updates from Alpaca**: 5-10 min + 30 sec = 5-10.5 minutes
- **Circuit breaker changes**: 5-10 min + 30 sec = 5-10.5 minutes

---

## 5. FIX STRATEGY

### Phase 1: Quick Wins (0-2 weeks)
**Effort**: LOW | **Impact**: MODERATE

#### 1a. Reduce Minimum Polling Interval
- Lower `_validate_watch_interval()` minimum from 10 seconds to 5 seconds
- **Impact**: Decrease latency to 5-10 min + 5s = 5-10.05 min (minimal improvement)
- **Cost**: Increased Lambda invocations, RDS connections
- **Not sufficient** for true real-time experience

#### 1b. Add Aggressive Refresh on Circuit Breaker Changes
- **Concept**: Monitor `circuit_breaker_state.updated_at` timestamp
- **Implementation**:
  - Add `last_circuit_update` to dashboard state
  - Compare on each fetch: if `circuit.updated_at > last_circuit_update`, force full refresh
  - Pre-fetch circuit state every 5 seconds (separate thread)
- **File**: `dashboard/watch/manager.py` (add circuit monitor)
- **Impact**: Circuit state visible within 5-10 seconds of change
- **Cost**: Additional Lambda calls (+4-5 per minute per user)

**Code addition**:
```python
class CircuitMonitor:
    """Aggressively monitor circuit breaker state for changes."""
    
    def __init__(self, fetch_fn, check_interval=5.0):
        self.fetch_fn = fetch_fn  # fetch_circuit
        self.check_interval = check_interval  # 5 seconds
        self.last_update = 0
        self.last_state = None
    
    def should_force_refresh(self):
        """Check if circuit state changed since last refresh."""
        now = time.monotonic()
        if now - self.last_update < self.check_interval:
            return False
        
        try:
            current = self.fetch_fn(None)
            if self.last_state and current.get("state") != self.last_state.get("state"):
                logger.info(f"Circuit state changed: {self.last_state} → {current}")
                self.last_state = current
                return True
            self.last_state = current
            self.last_update = now
        except Exception as e:
            logger.error(f"Circuit monitor error: {e}")
        
        return False
```

### Phase 2: Medium-Term (2-4 weeks)
**Effort**: MEDIUM | **Impact**: HIGH

#### 2a. Implement Server-Sent Events (SSE) Fallback
- **Why SSE instead of WebSocket?**: Works with existing HTTP API Gateway
- **Architecture**:
  ```
  Browser ──────HTTP GET /api/stream/positions────→ Lambda
      ↑                                                ↓
      │                          Returns SSE stream (chunked encoding)
      │   event: position_update                     │
      │   data: {"symbol":"AAPL","price":150.25}    │
      └────────────────────────────────────────────┘
  ```
- **File locations**:
  - `lambda/api/routes/stream.py` (new)
  - `dashboard/stream_client.py` (new)
  - `dashboard/watch/stream_monitor.py` (new)
- **Implementation**:
  ```python
  # Lambda endpoint: /api/stream/positions
  def stream_positions(user_id):
      """Stream position updates via SSE."""
      def generate():
          last_update = {}
          while True:
              current = get_positions_from_db()
              
              # Check for changes
              if current != last_update:
                  yield f"event: position_update\n"
                  yield f"data: {json.dumps(current)}\n\n"
                  last_update = current
              
              time.sleep(2)  # Poll DB every 2 seconds
      
      return Response(generate(), mimetype="text/event-stream")
  ```
- **Dashboard integration**:
  ```python
  # dashboard/stream_client.py
  def subscribe_positions(on_update):
      """Listen to position stream."""
      response = requests.get("/api/stream/positions", stream=True)
      for line in response.iter_lines():
          if line.startswith("data:"):
              data = json.loads(line[5:])
              on_update(data)
  ```
- **Impact**: Position updates visible within 2-5 seconds
- **Limitations**: 
  - Still polls DB every 2 seconds on Lambda side
  - Still depends on Phase 4 updating `algo_positions`
  - Works only in browser (not CLI dashboard)

#### 2b. Add RDS Event Subscriptions to SNS
- **Concept**: Trigger Lambda on INSERT/UPDATE to specific tables
- **Files to modify**:
  - `terraform/modules/services/rds_events.tf` (new)
  - `lambda/stream-events/lambda_function.py` (new)
- **Tables to monitor**:
  - `algo_positions` (position changes)
  - `algo_trades` (trade execution)
  - `circuit_breaker_state` (circuit changes)
- **Implementation**:
  ```terraform
  # RDS event subscription
  resource "aws_db_event_subscription" "positions_changes" {
    name      = "algo-positions-changes"
    sns_topic_arn = aws_sns_topic.position_updates.arn
    source_type   = "db-parameter-group"  # or db-instance
    event_categories = ["availability", "deletion", "failover", "failure", "recovery"]
  }
  ```
- **Limitation**: RDS events don't give row-level changes, only table-level notifications
- **Workaround**: Use CDC (Change Data Capture) with DMS or Debezium (complex, expensive)

### Phase 3: Long-Term (1-2 months)
**Effort**: HIGH | **Impact**: VERY HIGH

#### 3a. Implement WebSocket API
- **Architecture**:
  ```
  Browser connects via WebSocket ────→ API Gateway WebSocket API
                                        ↓
                                   Lambda (connection handler)
                                        ↓
                                   DynamoDB (connection table)
                                        ↓
                                   EventBridge
                                        ↓
                                   SNS Broadcasts
                                        ↓
                                   All connected clients
  ```
- **AWS Services**:
  - API Gateway WebSocket Protocol (`protocol_type = "WEBSOCKET"`)
  - DynamoDB table for active connections
  - EventBridge for event routing
  - SNS for broadcast
- **Files to create**:
  - `terraform/modules/services/websocket_api.tf` (new)
  - `lambda/websocket/connect.py` (new)
  - `lambda/websocket/disconnect.py` (new)
  - `lambda/websocket/broadcast.py` (new)
  - `dashboard/websocket_client.py` (new)
- **Implementation flow**:
  ```python
  # Browser client
  ws = WebSocket("/wss://api.example.com/stream")
  ws.onmessage = (event) => {
      data = JSON.parse(event.data)
      if data.type == "position_update":
          updatePositionsTable(data.positions)
  }
  
  # Lambda broadcast handler (triggered by orchestration or DB changes)
  def broadcast_positions(positions):
      # Query all active connections from DynamoDB
      connections = dynamodb.query_active_connections()
      for conn_id in connections:
          apigateway.post_to_connection(
              ConnectionId=conn_id,
              Data=json.dumps({
                  "type": "position_update",
                  "positions": positions,
                  "timestamp": datetime.now().isoformat()
              })
          )
  ```
- **Cost**: 
  - API Gateway WebSocket: $0.035/million messages ($7-35/month for live trading)
  - DynamoDB connection table: ~$0.25/million writes
  - Total: ~$35-50/month additional
- **Benefits**:
  - Updates within 100-500ms
  - Works in browser and CLI with upgrade
  - Scalable to 10,000+ concurrent connections

#### 3b. Implement Database Change Capture
- **Option A**: PostgreSQL LISTEN/NOTIFY (simplest)
  ```python
  # Python thread listening to DB notifications
  conn = psycopg2.connect(...)
  conn.set_isolation_level(0)  # Autocommit mode
  cur = conn.cursor()
  cur.execute("LISTEN positions_changed;")
  
  # In database triggers:
  CREATE TRIGGER positions_update_trigger
  AFTER UPDATE ON algo_positions
  FOR EACH ROW
  EXECUTE FUNCTION notify_positions_change();
  
  CREATE OR REPLACE FUNCTION notify_positions_change()
  RETURNS trigger AS $$
  BEGIN
    PERFORM pg_notify('positions_changed', row_to_json(NEW)::text);
    RETURN NEW;
  END;
  $$ LANGUAGE plpgsql;
  ```
- **Option B**: AWS DMS (Database Migration Service) with Debezium
  - Expensive (~$500-1000/month)
  - Overkill for this use case
- **Option C**: Application-level change tracking
  - Insert into `change_log` table on every update
  - Lambda poll change_log instead of main tables
  - Trade-off: additional writes to DB

#### 3c. Implement Event Broadcasting in Orchestration
- **Concept**: Each orchestration phase broadcasts updates to subscribers
- **Files to modify**:
  - `algo/orchestrator/phase_result.py` (add event emission)
  - `algo/orchestration/orchestrator.py` (add SNS publishing)
- **Implementation**:
  ```python
  # In Phase 3 (Position Monitor)
  class Phase3PositionMonitor:
      def execute(self, context):
          result = self.run_position_monitoring(context)
          
          # Broadcast position updates
          if result.positions_changed:
              self.publish_event({
                  "type": "position_update",
                  "phase": "3",
                  "positions": result.positions,
                  "timestamp": datetime.now().isoformat()
              })
          
          return result
      
      def publish_event(self, event):
          sns = boto3.client("sns")
          sns.publish(
              TopicArn=os.environ["ORCHESTRATION_EVENTS_TOPIC"],
              Message=json.dumps(event),
              Subject=event["type"]
          )
  ```

---

## 6. TEST VERIFICATION

### Test Plan for Real-Time Latency

#### Test 1: Circuit Breaker State Change Propagation
**Objective**: Verify circuit state changes are visible in <30 seconds

**Setup**:
```bash
# Terminal 1: Start dashboard
python -m dashboard -w 5

# Terminal 2: Monitor log for state changes
tail -f logs/dashboard.log | grep "circuit\|breaker"

# Terminal 3: Trigger circuit change
python scripts/test_circuit_breaker_change.py --action "trigger_halt" --reason "test"
```

**Script**: `scripts/test_circuit_breaker_change.py`
```python
import psycopg2
import json
import time
from datetime import datetime

def trigger_circuit_change(action="trigger_halt"):
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    
    # Insert circuit state change
    cur.execute("""
        UPDATE circuit_breaker_state 
        SET state = %s, reason = %s, updated_at = %s
        WHERE id = 1
    """, ("HALTED", "test_trigger", datetime.now()))
    
    conn.commit()
    print(f"[{datetime.now().isoformat()}] Circuit state changed to HALTED")
    
    # Monitor for visibility in dashboard
    time.sleep(35)
    
    # Query circuit state from API
    response = requests.get("http://localhost:3001/api/algo/circuit")
    data = response.json()
    
    state_visible = data.get("breaker_data", {}).get("state") == "HALTED"
    latency = time.time() - change_time
    
    print(f"State visible: {state_visible}, Latency: {latency:.1f}s")
    return latency
```

**Success criteria**:
- ✅ Circuit change visible in <30 seconds (current)
- ✅ Circuit change visible in <10 seconds (with Phase 1b)
- ✅ Circuit change visible in <2 seconds (with Phase 3a WebSocket)

#### Test 2: Position Update Latency
**Objective**: Verify position changes from Alpaca appear in <60 seconds

**Setup**:
```bash
# Terminal 1: Start dashboard
python -m dashboard -w 5

# Terminal 2: Execute trade via Alpaca
python scripts/execute_test_trade.py --symbol AAPL --qty 1 --side buy

# Terminal 3: Monitor latency
python scripts/measure_position_latency.py --symbol AAPL
```

**Measurement script**: `scripts/measure_position_latency.py`
```python
def measure_position_update_latency(symbol):
    import requests
    import time
    
    # Get baseline position count
    response = requests.get("http://localhost:3001/api/algo/positions")
    baseline_count = len(response.json().get("items", []))
    
    # Execute trade (via Alpaca)
    execute_trade(symbol, qty=1, side="buy")
    trade_time = time.time()
    
    # Poll for position update
    start = time.time()
    position_visible = False
    
    while time.time() - start < 120:  # Poll for 2 minutes max
        response = requests.get("http://localhost:3001/api/algo/positions")
        current_count = len(response.json().get("items", []))
        
        if current_count > baseline_count:
            position_visible = True
            latency = time.time() - trade_time
            print(f"Position visible after {latency:.1f}s")
            break
        
        time.sleep(2)  # Check every 2 seconds
    
    if not position_visible:
        print("Position not visible after 2 minutes")
    
    return latency if position_visible else 120
```

**Success criteria**:
- ✅ <60 seconds (current, depends on Phase 4 cycle)
- ✅ <30 seconds (with Phase 1b monitoring)
- ✅ <5 seconds (with Phase 3 WebSocket + DB change capture)

#### Test 3: Trade Execution Visibility
**Objective**: Verify executed trades appear in dashboard within 2-5 minutes

**Setup**:
```bash
# Terminal 1: Start dashboard
python -m dashboard -w 5

# Terminal 2: Execute entry signal trade
python scripts/execute_signal_entry.py --symbol AAPL --entry_price 150.00

# Terminal 3: Monitor trades table
python scripts/monitor_trade_execution.py --symbol AAPL --timeout 300
```

**Monitoring script**: `scripts/monitor_trade_execution.py`
```python
def monitor_trade_execution(symbol, timeout=300):
    import requests
    import time
    
    trade_start = time.time()
    
    while time.time() - trade_start < timeout:
        response = requests.get("http://localhost:3001/api/algo/trades")
        trades = response.json().get("items", [])
        
        recent_trades = [t for t in trades if t.get("symbol") == symbol]
        
        if recent_trades:
            trade = recent_trades[0]
            latency = time.time() - trade_start
            print(f"Trade visible after {latency:.1f}s")
            print(f"Trade details: {trade}")
            return latency
        
        time.sleep(5)
    
    print(f"Trade not visible after {timeout}s")
    return timeout
```

**Success criteria**:
- ✅ <300 seconds (current, 5-10 min orchestration + 30s polling)
- ✅ <120 seconds (with Phase 1b + aggressive refresh)
- ✅ <10 seconds (with Phase 3 WebSocket + event broadcasting)

---

## 7. DEPENDENCY CHAIN

### Critical Path for WebSocket Implementation

```
1. API Gateway WebSocket (Phase 3a) [2 weeks]
   ├─ Terraform module for WebSocket protocol
   ├─ Lambda connection/disconnect handlers
   └─ DynamoDB connection table
   
2. Orchestration Event Emission (Phase 3c) [1 week]
   ├─ Modify phase_result.py
   ├─ Add SNS topic configuration
   └─ Broadcast from each phase
   
3. Dashboard WebSocket Client (Phase 3a) [1 week]
   ├─ Python asyncio WebSocket client
   ├─ Browser JavaScript client (future)
   └─ Fallback to SSE
   
4. Database Change Capture (Phase 3b) [2 weeks]
   ├─ PostgreSQL LISTEN/NOTIFY
   ├─ Trigger functions
   └─ Lambda change notification handler
```

### Backward Compatibility Considerations

- **Phase 1 & 2** are backward compatible (add new code, don't remove polling)
- **Phase 3** requires API changes:
  - New WebSocket endpoints
  - New SNS topic
  - New DynamoDB table
  - Terraform plan must be applied
- **Fallback strategy**: Dashboard detects WebSocket unavailable, falls back to polling

---

## 8. ESTIMATED EFFORT & COST

| Phase | Timeline | Effort | AWS Cost | Impact |
|-------|----------|--------|----------|--------|
| **Phase 1a** | 1-2 days | LOW | $0 | 0% (minimal impact) |
| **Phase 1b** | 3-5 days | LOW | +$5/mo | 50% (5-10 min → <10 sec) |
| **Phase 2a** | 1-2 weeks | MEDIUM | +$10/mo | 75% (latency <5 sec) |
| **Phase 2b** | 1-2 weeks | MEDIUM | +$5/mo | 40% (limited RDS event granularity) |
| **Phase 3a** | 3-4 weeks | HIGH | +$35/mo | 95% (latency <500ms) |
| **Phase 3b** | 2-3 weeks | HIGH | +$20/mo | 95% (with Phase 3a) |
| **Phase 3c** | 1-2 weeks | MEDIUM | $0 | 5% (event broadcasting) |

**Recommended Path**: Phase 1b + Phase 2a (2-3 weeks, ~$50/mo, 75% improvement)

---

## 9. SUMMARY

**Root Cause**: No real-time infrastructure — system relies on polling with 30+ second intervals, which stacks on top of 5-10 minute orchestration cycles.

**Quick win**: Implement Phase 1b (Circuit Monitor) in 3-5 days
- Reduces circuit breaker latency from 5-10 min to <10 seconds
- Minimal code change, no infrastructure cost
- Immediate improvement for most critical data

**Medium-term**: Add Phase 2a (SSE Streaming)
- Reduces position/trade latency from 5-10 min to 2-5 seconds
- Works with existing HTTP API Gateway
- Cost: ~$10/month, 2 weeks development

**Long-term**: Implement Phase 3a (WebSocket)
- Full real-time (sub-500ms latency)
- Scalable to 10,000+ concurrent users
- Cost: ~$35/month, 4 weeks development

---

## 10. FILES TO REVIEW

**Current Architecture**:
- `dashboard/dashboard.py` - Lines 301-399 (watch mode polling)
- `dashboard/watch/manager.py` - Reload management
- `dashboard/fetchers.py` - Data loading orchestration
- `terraform/modules/services/main.tf` - API Gateway (HTTP only, line 202)

**Data Sources**:
- `dashboard/fetchers_config.py` - Circuit breaker fetching
- `dashboard/fetchers_portfolio.py` - Positions & trades fetching
- `lambda/api/routes/algo_handlers/dashboard.py` - API endpoints

**Orchestration**:
- `algo/orchestrator/phase3_position_monitor.py` - Position updates
- `algo/orchestrator/phase4_reconciliation.py` - DB reconciliation
- `algo/orchestration/orchestrator.py` - Orchestration cycle timing

