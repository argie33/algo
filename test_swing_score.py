#!/usr/bin/env python3
import psycopg2
import json
from datetime import date
from algo.algo_swing_score import SwingTraderScore

conn = psycopg2.connect(host='localhost', port=5432, database='stocks', user='stocks', password='stocks')
cur = conn.cursor()

scorer = SwingTraderScore(cur=cur)

symbols = ['CMPR', 'DBMF', 'ENFR', 'INVX', 'LB']
for sym in symbols:
    result = scorer.compute(sym, date(2026, 5, 18))
    print(f'{sym:6s} - pass={result.get("pass")}, reason={result.get("reason")}, score={result.get("swing_score")}')

cur.close()
conn.close()
