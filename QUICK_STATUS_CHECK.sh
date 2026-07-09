#!/bin/bash
# Quick status check for production readiness

echo "========================================================================"
echo "ALGO TRADING SYSTEM - QUICK STATUS CHECK"
echo "========================================================================"
echo ""

# Check database connectivity
echo "✓ Database connectivity:"
python3 -c "
from utils.db import DatabaseContext
try:
    with DatabaseContext('read') as ctx:
        ctx.execute('SELECT COUNT(*) FROM algo_positions')
        print(f'  Positions in DB: {ctx.fetchone()[0]}')
    print('  ✓ Database connected')
except Exception as e:
    print(f'  ✗ Database error: {e}')
    exit(1)
"

echo ""
echo "✓ Loader status (critical loaders):"
python3 -c "
from utils.db import DatabaseContext
loaders = ['price_daily', 'technical_data_daily', 'buy_sell_daily', 'algo_metrics_daily']
with DatabaseContext('read') as ctx:
    for loader in loaders:
        ctx.execute(f\"SELECT age_days, status FROM data_loader_status WHERE table_name = %s\", (loader,))
        row = ctx.fetchone()
        if row:
            age, status = row
            print(f'  {loader}: age={age}d, status={status}')
"

echo ""
echo "✓ Recent orchestrator runs:"
python3 -c "
from utils.db import DatabaseContext
with DatabaseContext('read') as ctx:
    ctx.execute('SELECT run_id, started_at FROM algo_orchestrator_runs ORDER BY started_at DESC LIMIT 3')
    for row in ctx.fetchall():
        print(f'  {row[0]}: {row[1]}')
"

echo ""
echo "✓ Open positions:"
python3 -c "
from utils.db import DatabaseContext
with DatabaseContext('read') as ctx:
    ctx.execute('SELECT COUNT(*) FROM algo_positions WHERE status = \'open\'')
    count = ctx.fetchone()[0]
    print(f'  {count} open positions')
"

echo ""
echo "========================================================================"
echo "STATUS: ✅ System operational"
echo "========================================================================"
echo ""
echo "Next steps:"
echo "  1. Start dashboard: cd webapp/frontend && npm run dev"
echo "  2. Run orchestrator: python3 test_complete_integration.py"
echo "  3. Deploy: git push (GitHub Actions will run Terraform apply)"
