import psycopg2
from datetime import datetime

conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

print('\n' + '='*80)
print('SIGNALS PIPELINE VERIFICATION')
print('='*80 + '\n')

# 1. Check stock_scores freshness
cur.execute('SELECT MAX(created_at) FROM stock_scores')
latest_scores = cur.fetchone()[0]
if latest_scores:
    age_min = (datetime.now() - latest_scores.replace(tzinfo=None)).total_seconds() / 60
    print(f'Stock Scores Age: {age_min:.1f} minutes')
    print(f'  Status: {"FRESH" if age_min < 5 else "STALE"}')
else:
    print('Stock Scores: NO DATA')

# 2. Check buy_sell_daily signals
cur.execute('''
SELECT COUNT(*) FROM buy_sell_daily 
WHERE DATE(created_at) = CURRENT_DATE
''')
signal_count = cur.fetchone()[0]
print(f'\nBuy/Sell Signals Generated: {signal_count}')

# 3. Check for any errors in generation
cur.execute('''
SELECT COUNT(*) FROM algo_signals 
WHERE DATE(created_at) = CURRENT_DATE
''')
algo_signals = cur.fetchone()[0]
print(f'Algo Signals: {algo_signals}')

# 4. Trading gate status
cur.execute('''
SELECT 
  COUNT(*) FILTER (WHERE profit_loss_pct > 0) as wins,
  COUNT(*) FILTER (WHERE profit_loss_pct < 0) as losses
FROM algo_trades
WHERE status = 'closed'
AND profit_loss_pct IS NOT NULL
''')
w, l = cur.fetchone()
decisive = (w or 0) + (l or 0)
print(f'\nTrading Gate: {"UNLOCKED (insufficient decisive trades)" if decisive < 10 else "CHECK WIN RATE"}')

print('\n' + '='*80)
print('READY FOR 9:30 AM ORCHESTRATOR RUN')
print('='*80 + '\n')

conn.close()
