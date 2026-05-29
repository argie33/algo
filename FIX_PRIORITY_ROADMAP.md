# Data Display Audit Fix Priority Roadmap

**Created:** 2026-05-28  
**Goal:** Deliver all 34 identified issues systematically  
**Time Estimate:** 4-5 hours for critical + high priority items

---

## PHASE 1: QUICK WINS (30 minutes)

These 3 actions have immediate visible impact:

### Step 1.1: Schedule Missing Loaders in Terraform (15 min)
**File:** `terraform/modules/loaders/main.tf`

Add EventBridge rules for 12 missing loaders. Check lines 288-465 for existing pattern, then add:

```terraform
# Signal Theme Loader
resource "aws_events_rule" "load_signal_themes" {
  name                = "${var.project_name}-load-signal-themes-${var.environment}"
  schedule_expression = "cron(35 9 * * MON-FRI *)"
  description         = "Load signal themes (momentum/reversal/breakout)"
  is_enabled          = true
}

resource "aws_events_target" "load_signal_themes" {
  rule      = aws_events_rule.load_signal_themes.name
  target_id = "load_signal_themes"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_signal_themes"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}

# Earnings Calendar Loader
resource "aws_events_rule" "load_earnings_calendar" {
  name                = "${var.project_name}-load-earnings-calendar-${var.environment}"
  schedule_expression = "cron(0 9 * * MON-FRI *)"
  description         = "Load earnings calendar"
  is_enabled          = true
}

resource "aws_events_target" "load_earnings_calendar" {
  rule      = aws_events_rule.load_earnings_calendar.name
  target_id = "load_earnings_calendar"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_earnings_calendar"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}

# Sentiment Loaders (9 total)
# load_analyst_sentiment_analysis
resource "aws_events_rule" "load_analyst_sentiment_analysis" {
  name                = "${var.project_name}-load-analyst-sentiment-${var.environment}"
  schedule_expression = "cron(0 8 * * MON-FRI *)"  # 8:00 UTC = 4:00 AM ET
  description         = "Load analyst sentiment"
  is_enabled          = true
}

resource "aws_events_target" "load_analyst_sentiment_analysis" {
  rule      = aws_events_rule.load_analyst_sentiment_analysis.name
  target_id = "load_analyst_sentiment_analysis"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_analyst_sentiment_analysis"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}

# load_analyst_upgrade_downgrade
resource "aws_events_rule" "load_analyst_upgrade_downgrade" {
  name                = "${var.project_name}-load-analyst-upgrades-${var.environment}"
  schedule_expression = "cron(5 8 * * MON-FRI *)"
  is_enabled          = true
}

resource "aws_events_target" "load_analyst_upgrade_downgrade" {
  rule      = aws_events_rule.load_analyst_upgrade_downgrade.name
  target_id = "load_analyst_upgrade_downgrade"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_analyst_upgrade_downgrade"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}

# load_aaii_sentiment
resource "aws_events_rule" "load_aaii_sentiment" {
  name                = "${var.project_name}-load-aaii-sentiment-${var.environment}"
  schedule_expression = "cron(10 8 * * MON-FRI *)"
  is_enabled          = true
}

resource "aws_events_target" "load_aaii_sentiment" {
  rule      = aws_events_rule.load_aaii_sentiment.name
  target_id = "load_aaii_sentiment"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_aaii_sentiment"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}

# load_fear_greed_index
resource "aws_events_rule" "load_fear_greed_index" {
  name                = "${var.project_name}-load-fear-greed-${var.environment}"
  schedule_expression = "cron(15 8 * * MON-FRI *)"
  is_enabled          = true
}

resource "aws_events_target" "load_fear_greed_index" {
  rule      = aws_events_rule.load_fear_greed_index.name
  target_id = "load_fear_greed_index"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_fear_greed_index"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}

# load_naaim
resource "aws_events_rule" "load_naaim" {
  name                = "${var.project_name}-load-naaim-${var.environment}"
  schedule_expression = "cron(20 8 * * MON-FRI *)"
  is_enabled          = true
}

resource "aws_events_target" "load_naaim" {
  rule      = aws_events_rule.load_naaim.name
  target_id = "load_naaim"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_naaim"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}

# load_sentiment
resource "aws_events_rule" "load_sentiment" {
  name                = "${var.project_name}-load-sentiment-${var.environment}"
  schedule_expression = "cron(25 8 * * MON-FRI *)"
  is_enabled          = true
}

resource "aws_events_target" "load_sentiment" {
  rule      = aws_events_rule.load_sentiment.name
  target_id = "load_sentiment"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_sentiment"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}

# load_sentiment_social
resource "aws_events_rule" "load_sentiment_social" {
  name                = "${var.project_name}-load-sentiment-social-${var.environment}"
  schedule_expression = "cron(30 8 * * MON-FRI *)"
  is_enabled          = true
}

resource "aws_events_target" "load_sentiment_social" {
  rule      = aws_events_rule.load_sentiment_social.name
  target_id = "load_sentiment_social"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_sentiment_social"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}

# load_signal_quality_scores
resource "aws_events_rule" "load_signal_quality_scores" {
  name                = "${var.project_name}-load-signal-quality-${var.environment}"
  schedule_expression = "cron(40 9 * * MON-FRI *)"
  is_enabled          = true
}

resource "aws_events_target" "load_signal_quality_scores" {
  rule      = aws_events_rule.load_signal_quality_scores.name
  target_id = "load_signal_quality_scores"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_signal_quality_scores"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}

# load_signal_trade_performance
resource "aws_events_rule" "load_signal_trade_performance" {
  name                = "${var.project_name}-load-signal-trade-perf-${var.environment}"
  schedule_expression = "cron(45 9 * * MON-FRI *)"
  is_enabled          = true
}

resource "aws_events_target" "load_signal_trade_performance" {
  rule      = aws_events_rule.load_signal_trade_performance.name
  target_id = "load_signal_trade_performance"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_signal_trade_performance"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}
```

**Verification after Terraform apply:**
```bash
aws events list-rules --name-prefix "algo-load" | jq '.Rules | length'
# Expected: 26+ (all loaders scheduled)
```

---

### Step 1.2: Manually Run Loaders Once (10 min)

Run each missing loader to backfill initial data:

```bash
# Sentiment loaders (parallel)
python3 loaders/load_analyst_sentiment_analysis.py &
python3 loaders/load_analyst_upgrade_downgrade.py &
python3 loaders/load_aaii_sentiment.py &
python3 loaders/load_fear_greed_index.py &
python3 loaders/load_naaim.py &
python3 loaders/load_sentiment.py &
python3 loaders/load_sentiment_social.py &

# Signal loaders
python3 loaders/load_signal_themes.py &
python3 loaders/load_signal_quality_scores.py &
python3 loaders/load_signal_trade_performance.py &

# Earnings calendar
python3 loaders/load_earnings_calendar.py &

# Wait for all
wait
```

---

### Step 1.3: Verify Data Populated (5 min)

Run these SQL queries:

```sql
SELECT 'signal_themes' as table_name, COUNT(*) as rows FROM signal_themes
UNION ALL SELECT 'analyst_sentiment_analysis', COUNT(*) FROM analyst_sentiment_analysis
UNION ALL SELECT 'analyst_upgrade_downgrade', COUNT(*) FROM analyst_upgrade_downgrade
UNION ALL SELECT 'aaii_sentiment', COUNT(*) FROM aaii_sentiment
UNION ALL SELECT 'fear_greed_index', COUNT(*) FROM fear_greed_index
UNION ALL SELECT 'naaim', COUNT(*) FROM naaim
UNION ALL SELECT 'sentiment', COUNT(*) FROM sentiment
UNION ALL SELECT 'sentiment_social', COUNT(*) FROM sentiment_social
UNION ALL SELECT 'earnings_calendar', COUNT(*) FROM earnings_calendar
UNION ALL SELECT 'signal_quality_scores', COUNT(*) FROM signal_quality_scores
UNION ALL SELECT 'signal_trade_performance', COUNT(*) FROM signal_trade_performance;
```

Expected: All counts > 0

---

## PHASE 2: API ENHANCEMENTS (60 minutes)

### Step 2.1: Verify Metric Loaders Populated (15 min)

Check all metric tables have data:

```sql
SELECT 'key_metrics' as table_name, COUNT(*) as rows, COUNT(market_cap) as with_cap FROM key_metrics
UNION ALL SELECT 'value_metrics', COUNT(*), COUNT(pe_ratio) FROM value_metrics
UNION ALL SELECT 'quality_metrics', COUNT(*), COUNT(roe) FROM quality_metrics
UNION ALL SELECT 'growth_metrics', COUNT(*), COUNT(revenue_growth_yoy) FROM growth_metrics
UNION ALL SELECT 'stability_metrics', COUNT(*), COUNT(beta) FROM stability_metrics
UNION ALL SELECT 'positioning_metrics', COUNT(*), COUNT(institutional_ownership) FROM positioning_metrics;
```

If any table is empty or has too many NULLs, manually trigger that loader:
```bash
python3 loaders/load_key_metrics.py
python3 loaders/load_value_metrics.py
python3 loaders/load_quality_metrics.py
python3 loaders/load_growth_metrics.py
python3 loaders/load_stability_metrics.py
python3 loaders/load_positioning_metrics.py
```

---

### Step 2.2: Add Data Freshness Check to API (30 min)

**File:** `lambda/api/routes/utils.py`

Add function:
```python
from datetime import datetime, timedelta
from typing import Dict, Optional

def check_data_freshness(table_name: str, date_column: str = "date", warning_days: int = 1) -> Dict:
    """Check how fresh data is in a table."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT MAX({date_column}) as max_date 
            FROM {table_name}
        """)
        result = cursor.fetchone()
        
    if not result or not result[0]:
        return {"data_age_days": None, "is_stale": True, "warning": "No data found"}
    
    max_date = result[0]
    if isinstance(max_date, str):
        max_date = datetime.fromisoformat(max_date).date()
    
    data_age = (datetime.now().date() - max_date).days
    is_stale = data_age > warning_days
    
    return {
        "data_age_days": data_age,
        "is_stale": is_stale,
        "max_date": str(max_date),
        "warning": f"Data is {data_age} days old" if is_stale else None
    }
```

Update API routes to include freshness checks:

**File:** `lambda/api/routes/signals.py` (around line 62)

```python
# After main query, add freshness check
freshness = check_data_freshness("buy_sell_daily", "date", warning_days=1)

response = {
    "items": items,
    "total": total,
    "data_freshness": freshness,  # NEW
    "limit": limit,
    "offset": offset
}
```

**File:** `lambda/api/routes/scores.py` (around line 119)

```python
freshness = check_data_freshness("stock_scores", "updated_at", warning_days=7)

response = {
    "items": items,
    "total": total,
    "data_freshness": freshness,  # NEW
    "limit": limit,
    "offset": offset
}
```

**File:** `lambda/api/routes/market.py` (around line XX)

```python
freshness = check_data_freshness("market_health_daily", "date", warning_days=1)

response = {
    "vix_level": data.vix_level,
    "advance_decline_ratio": data.advance_decline_ratio,
    # ... other fields
    "data_freshness": freshness,  # NEW
    "timestamp": datetime.now().isoformat()
}
```

---

### Step 2.3: Update /api/health Endpoint (15 min)

**File:** `lambda/api/routes/health.py`

Replace with comprehensive version:

```python
from datetime import datetime
from .utils import check_data_freshness, get_db_connection

def health_check():
    """Comprehensive system health check."""
    
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database": "disconnected",
        "checks": {}
    }
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            health["database"] = "connected"
    except Exception as e:
        health["status"] = "critical"
        health["database"] = "disconnected"
        health["error"] = str(e)
        return health, 503
    
    # Check price data freshness
    price_freshness = check_data_freshness("price_daily", "date", warning_days=1)
    health["checks"]["price_data"] = price_freshness
    if price_freshness["is_stale"]:
        health["status"] = "degraded"
    
    # Check technical data freshness
    tech_freshness = check_data_freshness("technical_data_daily", "date", warning_days=1)
    health["checks"]["technical_data"] = tech_freshness
    if tech_freshness["is_stale"] and health["status"] == "healthy":
        health["status"] = "degraded"
    
    # Check signal data freshness
    signal_freshness = check_data_freshness("buy_sell_daily", "date", warning_days=1)
    health["checks"]["signal_data"] = signal_freshness
    
    # Check orchestrator status
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT created_at FROM algo_audit_log 
                ORDER BY created_at DESC LIMIT 1
            """)
            result = cursor.fetchone()
            if result:
                last_run = result[0]
                age_hours = (datetime.now() - last_run).total_seconds() / 3600
                health["checks"]["orchestrator"] = {
                    "last_run": str(last_run),
                    "age_hours": round(age_hours, 1),
                    "is_stale": age_hours > 4
                }
                if age_hours > 4:
                    health["status"] = "degraded"
    except Exception as e:
        health["checks"]["orchestrator"] = {"error": str(e)}
    
    status_code = 200 if health["status"] == "healthy" else (503 if health["status"] == "critical" else 200)
    return health, status_code

@router.get("/health")
def get_health():
    health, status_code = health_check()
    return health, status_code
```

---

## PHASE 3: FRONTEND IMPROVEMENTS (90 minutes)

### Step 3.1: Add Error Logging (20 min)

**File:** `webapp/frontend/src/utils/apiClient.js`

Add logging wrapper:

```javascript
const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:5000';

const apiCall = async (endpoint, options = {}) => {
  try {
    const response = await fetch(`${API_BASE}${endpoint}`, options);
    const data = await response.json();
    
    // Log freshness warnings
    if (data.data_freshness?.is_stale) {
      console.warn(`⚠️ Stale data from ${endpoint}: ${data.data_freshness.warning}`);
    }
    
    // Log missing required fields
    if (data.items && data.items.length > 0) {
      const item = data.items[0];
      // Check for unexpected NULLs
      const requiredFields = endpoint.includes('scores') 
        ? ['symbol', 'momentum_score', 'composite_score']
        : endpoint.includes('signals')
        ? ['symbol', 'ema_21', 'adx', 'signal']
        : [];
      
      for (const field of requiredFields) {
        if (item[field] == null) {
          console.error(`❌ Expected field "${field}" is NULL in ${endpoint}`);
        }
      }
    }
    
    return data;
  } catch (error) {
    console.error(`API Error on ${endpoint}:`, error);
    throw error;
  }
};

export default apiCall;
```

---

### Step 3.2: Show Data Completeness (20 min)

**File:** `webapp/frontend/src/components/DataQualityBadge.jsx`

Create new component:

```jsx
import React, { useEffect, useState } from 'react';

const DataQualityBadge = ({ apiEndpoint, requiredFields = [] }) => {
  const [completeness, setCompleteness] = useState(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(apiEndpoint);
        const data = await response.json();
        
        if (data.items && data.items.length > 0) {
          let completeCount = 0;
          
          data.items.forEach(item => {
            let hasAllFields = true;
            requiredFields.forEach(field => {
              if (item[field] == null) hasAllFields = false;
            });
            if (hasAllFields) completeCount++;
          });
          
          const pct = Math.round((completeCount / data.items.length) * 100);
          setCompleteness(pct);
        }
      } catch (error) {
        console.error('Failed to check data completeness:', error);
      } finally {
        setLoading(false);
      }
    };
    
    fetchData();
  }, [apiEndpoint]);
  
  if (loading) return <span className="badge badge-info">Loading...</span>;
  if (!completeness) return null;
  
  const color = completeness >= 80 ? 'success' : completeness >= 50 ? 'warning' : 'danger';
  return (
    <span className={`badge badge-${color}`}>
      Data Quality: {completeness}%
    </span>
  );
};

export default DataQualityBadge;
```

Use in components:
```jsx
<DataQualityBadge 
  apiEndpoint="/api/scores?limit=500"
  requiredFields={['momentum_score', 'composite_score', 'symbol']}
/>
```

---

### Step 3.3: Add Data Age Badges (30 min)

**File:** `webapp/frontend/src/components/DataAgeBadge.jsx`

```jsx
import React from 'react';

const DataAgeBadge = ({ dataFreshness }) => {
  if (!dataFreshness) return null;
  
  const { data_age_days, is_stale } = dataFreshness;
  
  if (data_age_days === null) {
    return <span className="badge badge-danger">❌ No Data</span>;
  }
  
  let color, icon;
  if (data_age_days === 0) {
    color = 'success';
    icon = '✓';
  } else if (data_age_days === 1) {
    color = 'info';
    icon = '✓';
  } else if (data_age_days <= 3) {
    color = 'warning';
    icon = '⚠️';
  } else {
    color = 'danger';
    icon = '❌';
  }
  
  return (
    <span className={`badge badge-${color}`} title={`Last updated ${data_age_days} day(s) ago`}>
      {icon} Updated {data_age_days}d ago
    </span>
  );
};

export default DataAgeBadge;
```

Update dashboard components to show badges:

**File:** `webapp/frontend/src/pages/ScoresDashboard.jsx` (around line 50)

```jsx
import DataAgeBadge from '../components/DataAgeBadge';

export default function ScoresDashboard() {
  const [scores, setScores] = useState(null);
  const [dataFreshness, setDataFreshness] = useState(null);
  
  useEffect(() => {
    // ... existing fetch code
    const data = await fetchScores();
    setScores(data.items);
    setDataFreshness(data.data_freshness);  // NEW
  }, []);
  
  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <DataAgeBadge dataFreshness={dataFreshness} />
      </div>
      {/* ... rest of component */}
    </div>
  );
}
```

---

### Step 3.4: Handle Missing Data Gracefully (20 min)

**File:** `webapp/frontend/src/components/ScoreCard.jsx`

```jsx
const ScoreCard = ({ score }) => {
  const formatValue = (value, label) => {
    if (value == null) {
      console.warn(`Missing value for ${label}`);
      return '—';
    }
    if (isNaN(Number(value))) {
      console.error(`Invalid value for ${label}: ${value}`);
      return '—';
    }
    return Number(value).toFixed(1);
  };
  
  return (
    <div className="card">
      <div className="card-header">
        <h5>{score.symbol}</h5>
      </div>
      <div className="card-body">
        {!score.momentum_score && (
          <div className="alert alert-warning small">
            ⚠️ Momentum score unavailable — may be loading or data missing
          </div>
        )}
        <p>
          <strong>Momentum:</strong> {formatValue(score.momentum_score, 'momentum_score')}
        </p>
        <p>
          <strong>Composite:</strong> {formatValue(score.composite_score, 'composite_score')}
        </p>
        {/* ... more fields */}
      </div>
    </div>
  );
};
```

---

## PHASE 4: DATA COVERAGE (60 minutes)

### Step 4.1: Add Russell 2000 Loader (60 min)

**File:** `loaders/load_russell2000_constituents.py` (NEW)

Create:

```python
"""Load Russell 2000 (small-cap) index constituents."""

import logging
import json
from datetime import datetime
import yfinance as yf
from database import get_db_connection, exec_statement

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RUSSELL_2000_TICKERS = [
    # First 50 small-cap stocks (demonstrative)
    "AGII", "ACET", "ACIU", "ACTU", "ACNX", "ACOP", "ACQU", "ACRX", "ACTS",
    # ... (full list of 2000 tickers)
]

def load_russell2000():
    """Load Russell 2000 constituents into stock_symbols table."""
    
    logger.info("Starting Russell 2000 load")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        for ticker in RUSSELL_2000_TICKERS:
            try:
                # Get basic info
                stock = yf.Ticker(ticker)
                info = stock.info
                
                # Insert or update
                cursor.execute("""
                    INSERT INTO stock_symbols (
                        symbol, company_name, sector, industry, market_cap_billions,
                        index_membership, last_updated, universe
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        index_membership = EXCLUDED.index_membership,
                        market_cap_billions = EXCLUDED.market_cap_billions,
                        universe = EXCLUDED.universe,
                        last_updated = EXCLUDED.last_updated
                """, (
                    ticker,
                    info.get('longName', ticker),
                    info.get('sector', 'Unknown'),
                    info.get('industry', 'Unknown'),
                    info.get('marketCap', 0) / 1e9 if info.get('marketCap') else None,
                    'Russell 2000',
                    datetime.now(),
                    'Russell 2000'  # NEW COLUMN
                ))
            except Exception as e:
                logger.warning(f"Failed to load {ticker}: {e}")
        
        conn.commit()
    
    logger.info(f"Completed Russell 2000 load: {len(RUSSELL_2000_TICKERS)} symbols")

if __name__ == "__main__":
    load_russell2000()
```

Add to Terraform schedule:

**File:** `terraform/modules/loaders/main.tf`

```terraform
resource "aws_events_rule" "load_russell2000_constituents" {
  name                = "${var.project_name}-load-russell2000-${var.environment}"
  schedule_expression = "cron(0 8 * * MON *)"  # Weekly Monday
  description         = "Load Russell 2000 constituents"
  is_enabled          = true
}

resource "aws_events_target" "load_russell2000_constituents" {
  rule      = aws_events_rule.load_russell2000_constituents.name
  target_id = "load_russell2000_constituents"
  arn       = aws_ecs_cluster.loaders.arn
  role_arn  = aws_iam_role.loader_role.arn
  
  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loader_tasks["load_russell2000_constituents"].arn
    cluster                 = aws_ecs_cluster.loaders.name
    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.loaders.id]
      assign_public_ip = false
    }
  }
}
```

---

## IMPLEMENTATION CHECKLIST

### Phase 1: Quick Wins (30 min)
- [ ] Add 12 EventBridge rules to terraform/modules/loaders/main.tf
- [ ] Apply Terraform changes
- [ ] Manually run all missing loaders
- [ ] Verify SQL: All new tables have rows
- [ ] Commit: "feat: Schedule 12 missing data loaders"

### Phase 2: API (60 min)
- [ ] Create `lambda/api/routes/utils.py` with freshness check function
- [ ] Update `/api/signals` endpoint to include `data_freshness`
- [ ] Update `/api/scores` endpoint to include `data_freshness`
- [ ] Update `/api/market` endpoint to include `data_freshness`
- [ ] Rewrite `/api/health` with comprehensive checks
- [ ] Test all endpoints with curl
- [ ] Commit: "feat: Add data freshness checks to API endpoints"

### Phase 3: Frontend (90 min)
- [ ] Update `apiClient.js` with error logging
- [ ] Create `DataQualityBadge.jsx` component
- [ ] Create `DataAgeBadge.jsx` component
- [ ] Update `ScoresDashboard.jsx` to show badges
- [ ] Update `MarketsHealth.jsx` to show VIX age badge
- [ ] Update score cards to handle NULL gracefully
- [ ] Test in browser (npm start)
- [ ] Commit: "feat: Add data quality/age badges to frontend"

### Phase 4: Data Coverage (60 min)
- [ ] Create `loaders/load_russell2000_constituents.py`
- [ ] Add Russell 2000 EventBridge rule to terraform
- [ ] Apply Terraform
- [ ] Test loader manually
- [ ] Update API/frontend filters to show "S&P 500 / Russell 2000"
- [ ] Commit: "feat: Add Russell 2000 small-cap stock coverage"

### Phase 5: Verification (30 min)
- [ ] Run full verification checklist (see below)
- [ ] Test each API endpoint with curl
- [ ] Open frontend and verify:
  - /app/scores shows data completeness badge
  - /app/signals shows age badge
  - /app/market shows VIX + timestamp
  - /app/portfolio shows empty state or positions
- [ ] Create tag: `audit-fixes-complete-2026-05-28`

---

## VERIFICATION CHECKLIST

### API Endpoints
```bash
# Test data freshness in responses
curl http://localhost:5000/api/signals?limit=1 | jq '.data_freshness'
curl http://localhost:5000/api/scores?limit=1 | jq '.data_freshness'
curl http://localhost:5000/api/market/status | jq '.data_freshness'

# Test health endpoint
curl http://localhost:5000/api/health | jq '.checks'

# Test specific fields are no longer NULL
curl http://localhost:5000/api/signals?limit=1 | jq '.items[0] | {symbol, ema_21, adx, signal_quality_score}'
# Expected: Real numbers, not null

curl http://localhost:5000/api/scores?limit=1 | jq '.items[0] | {symbol, momentum_score, composite_score}'
# Expected: Real numbers, not null
```

### Frontend
```bash
cd webapp/frontend
npm start
# Open http://localhost:3000

# Check pages
- /app/scores → Data Quality badge shows ≥80%
- /app/signals → Updated badge shows "0d ago" or "1d ago"
- /app/market → VIX shows with timestamp (not NULL)
- /app/portfolio → Shows positions or "No positions yet" (not crashed)
```

### Database
```sql
-- Verify all tables populated
SELECT table_name, COUNT(*) as rows FROM (
  SELECT 'signal_themes' as table_name FROM signal_themes
  UNION ALL SELECT 'analyst_sentiment_analysis' FROM analyst_sentiment_analysis
  UNION ALL SELECT 'earnings_calendar' FROM earnings_calendar
  -- ... more tables
) counts GROUP BY table_name;

-- Verify no recent NULL values
SELECT COUNT(*) FROM buy_sell_daily 
WHERE date = CURRENT_DATE - 1 AND (ema_21 IS NULL OR adx IS NULL);
-- Expected: 0 (no recent NULLs)
```

---

## SUCCESS CRITERIA

You're done when ALL of these are true:

✅ **Loaders**
- [ ] 12 missing loaders scheduled in EventBridge
- [ ] All loaders run daily without errors
- [ ] `SELECT COUNT(*) FROM signal_themes` > 0

✅ **API**
- [ ] `/api/signals` returns real ema_21, adx, mansfield_rs (not NULL)
- [ ] `/api/scores` returns real momentum_score, composite_score (not NULL)
- [ ] `/api/market` returns vix_level with timestamp
- [ ] All endpoints include `data_freshness` field
- [ ] `/api/health` returns comprehensive status

✅ **Frontend**
- [ ] ScoresDashboard shows "Data Quality: 85%+" badge
- [ ] Signals page shows "Updated 0d ago" badge (green)
- [ ] Markets page shows "VIX 18.5 (updated 2h ago)" with color
- [ ] No dashes (—) in primary data fields
- [ ] Console has no "Expected field X is NULL" errors

✅ **Coverage**
- [ ] Russell 2000 loader running weekly
- [ ] S&P 500 + Russell 2000 options in UI filters
- [ ] No more "2000 small-cap stocks missing"

---

**Total Implementation Time:** 4-5 hours  
**Recommended Schedule:**
- Day 1: Phase 1 (Quick Wins) + Phase 2 (API) = 90 min
- Day 2: Phase 3 (Frontend) = 90 min
- Day 3: Phase 4 (Coverage) + Phase 5 (Verification) = 90 min

---

**Roadmap Version:** 1.0  
**Last Updated:** 2026-05-28  
**Status:** Ready to implement
