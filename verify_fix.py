#!/usr/bin/env python3
from utils.db.context import DatabaseContext
with DatabaseContext("read") as cur:
    cur.execute("SELECT value FROM algo_config WHERE key='max_positions'")
    val = cur.fetchone()[0]
    print(f"max_positions in DB: {val}")
