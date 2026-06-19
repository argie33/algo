# Loader Safeguards: Preventing Hung Loaders

Three layers prevent indefinite loader runs:

1. **Step Functions Timeout:** Hard timeout in Terraform (stock_prices_daily 6h, swing_trader_scores 2h, technical_data_daily 2h, market_health_daily 20m)
2. **Timeout Guardian Lambda:** Runs every 5 min, kills ECS tasks exceeding MAX_DURATION (price 4h, technical/score 2h, others 1h), updates status to TIMEOUT
3. **Database Constraint:** data_loader_status CHECK prevents RUNNING status > 24h

**Code:** `lambda/loader_timeout_guardian.py` (enforces max runtime per loader type)
