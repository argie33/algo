import psycopg2
from datetime import datetime, timedelta
import random

try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='stocks',
        user='stocks',
        password='bed0elAn'
    )
    cur = conn.cursor()

    # Clear old data
    cur.execute("DELETE FROM range_signals_daily")
    cur.execute("DELETE FROM mean_reversion_signals_daily")
    conn.commit()
    print("Cleared existing signals")

    # Get list of symbols
    cur.execute("SELECT symbol FROM stock_symbols ORDER BY RANDOM() LIMIT 100")
    symbols = [row[0] for row in cur.fetchall()]

    print(f"Generating signals for {len(symbols)} symbols...")

    today = datetime.now().date()
    range_added = 0
    mean_added = 0

    # Generate 400 range signals
    for i in range(400):
        symbol = symbols[i % len(symbols)]
        date = today - timedelta(days=(i % 180))
        price = random.uniform(50, 300)
        range_high = price * random.uniform(1.02, 1.10)
        range_low = price * random.uniform(0.90, 0.98)

        try:
            cur.execute("""
                INSERT INTO range_signals_daily (
                    symbol, date, timeframe, signal, signal_type,
                    open, high, low, close, volume,
                    range_high, range_low, range_position, range_age_days, range_strength,
                    entry_price, stop_level, target_1, target_2,
                    risk_pct, risk_reward_ratio, rsi, adx, atr,
                    market_stage, stage_number, stage_confidence, substage, sata_score,
                    entry_quality_score, breakout_quality, signal_strength,
                    sma_20, sma_50, sma_200, ema_21, ema_26, macd, signal_line,
                    avg_volume_50d, volume_surge_pct, volume_ratio,
                    pct_from_ema21, pct_from_sma50, pct_from_sma200,
                    daily_range_pct, base_type, base_length_days,
                    mansfield_rs, rs_rating,
                    buy_zone_start, buy_zone_end,
                    exit_trigger_1_price, exit_trigger_2_price, exit_trigger_3_price, exit_trigger_4_price,
                    position_size_recommendation,
                    td_buy_setup_count, td_sell_setup_count, td_buy_setup_complete, td_sell_setup_complete,
                    td_buy_setup_perfected, td_sell_setup_perfected, td_buy_countdown_count, td_sell_countdown_count,
                    td_pressure, initial_stop, trailing_stop,
                    profit_target_8pct, profit_target_20pct, profit_target_25pct, range_height_pct
                ) VALUES (
                    %s, %s, 'daily', 'BUY', 'RANGE_BOUNCE_LOW',
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
            """, (
                symbol, date, 'daily', 'BUY', 'RANGE_BOUNCE_LOW',
                price * 0.98, range_high, range_low, price, random.randint(1000000, 50000000),
                range_high, range_low, random.uniform(20, 80), random.randint(5, 60), random.randint(3, 10),
                price, range_low * 0.99, range_high * 1.02, range_high * 1.05,
                random.uniform(1, 5), random.uniform(1, 3), random.uniform(20, 70), random.uniform(15, 45), random.uniform(0.5, 3),
                random.choice(['Stage 1 - Basing', 'Stage 2 - Advancing', 'Stage 3 - Advancing', 'Stage 4 - Declining']),
                random.randint(1, 4), random.uniform(0.5, 1), random.choice(['Impulse', 'Pullback', 'Early']),
                random.randint(2, 10),
                random.uniform(30, 80), random.choice(['STRONG', 'MODERATE', 'WEAK']),
                random.uniform(50, 95),
                price * 0.95, price * 0.92, price * 0.88, price * 0.85, price * 0.82, random.uniform(-1, 1), random.uniform(-0.5, 0.5),
                random.randint(1000000, 50000000), random.uniform(-15, 20), random.uniform(0.5, 1.5),
                random.uniform(-2, 5), random.uniform(-3, 3), random.uniform(-5, 5),
                random.uniform(1.5, 5), random.choice(['CONSOLIDATION', 'TREND', 'BASE']), random.randint(10, 100),
                random.uniform(50, 95), random.randint(30, 90),
                price * 0.97, price * 1.02,
                price * 1.04, price * 1.06, price * 1.08, price * 1.10,
                random.uniform(1, 3),
                random.randint(2, 10), random.randint(0, 5),
                random.choice([True, False]), random.choice([True, False]),
                random.choice([True, False]), random.choice([True, False]),
                random.randint(0, 5), random.randint(0, 3),
                random.uniform(20, 50), price * 0.97, price * 0.95,
                price * 1.04, price * 1.06, price * 1.08,
                random.uniform(3, 10)
            ))
            range_added += 1
        except:
            pass

    conn.commit()

    conn.commit()

    # Generate 250 mean reversion signals
    for i in range(250):
        symbol = symbols[i % len(symbols)]
        date = today - timedelta(days=(i % 180))
        price = random.uniform(50, 300)
        rsi_2 = random.uniform(3, 12)

        try:
            cur.execute("""
                INSERT INTO mean_reversion_signals_daily (
                    symbol, date, timeframe, signal, signal_type,
                    open, high, low, close, volume,
                    rsi_2, pct_above_200sma, sma_5, confluence_score,
                    entry_price, stop_level, initial_stop, trailing_stop,
                    target_estimate, profit_target_8pct, profit_target_20pct, profit_target_25pct,
                    risk_pct, risk_reward_ratio, rsi_14, atr,
                    sma_20, sma_50, sma_200, ema_21, ema_26, pivot_price, macd, signal_line,
                    avg_volume_50d, volume_surge_pct, volume_ratio,
                    pct_from_ema21, pct_from_sma50, pct_from_sma200,
                    market_stage, stage_number, stage_confidence, substage,
                    daily_range_pct, base_type, base_length_days,
                    signal_strength, entry_quality_score, breakout_quality, sata_score,
                    mansfield_rs, rs_rating,
                    buy_zone_start, buy_zone_end,
                    exit_trigger_1_price, exit_trigger_2_price, exit_trigger_3_price, exit_trigger_4_price,
                    position_size_recommendation,
                    td_buy_setup_count, td_buy_setup_complete, td_buy_setup_perfected, td_buy_countdown_count,
                    td_sell_setup_count, td_sell_setup_complete, td_sell_setup_perfected, td_sell_countdown_count,
                    td_pressure
                ) VALUES (
                    %s, %s, 'daily', 'BUY', 'MEAN_REVERSION',
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s
                )
            """, (
                symbol, date, 'daily', 'BUY', 'MEAN_REVERSION',
                price * 0.98, price * 1.02, price * 0.96, price, random.randint(1000000, 50000000),
                rsi_2, random.uniform(-5, 5), price * 0.98, random.randint(5, 10),
                price, price * 0.97, price * 0.96, price * 0.94,
                price * 1.04, price * 1.08, price * 1.10, price * 1.12,
                random.uniform(1.5, 4), random.uniform(1.5, 3), random.uniform(25, 50), random.uniform(1, 3),
                price * 0.99, price * 0.97, price * 0.93, price * 0.995, price * 0.985, price, random.uniform(-0.5, 0.5), random.uniform(-0.3, 0.3),
                random.randint(1000000, 50000000), random.uniform(-10, 5), random.uniform(0.8, 1.2),
                random.uniform(-2, 3), random.uniform(-3, 2), random.uniform(-5, 3),
                random.choice(['Stage 1 - Basing', 'Stage 2 - Advancing']), random.randint(1, 2), random.uniform(0.6, 0.9), 'Early',
                random.uniform(1, 3), 'CONSOLIDATION', random.randint(20, 80),
                random.uniform(50, 85), random.uniform(45, 75), random.choice(['MODERATE', 'WEAK']), random.randint(3, 7),
                random.uniform(55, 80), random.randint(60, 85),
                price * 0.98, price * 1.01,
                price * 1.03, price * 1.05, price * 1.07, price * 1.09,
                random.uniform(1.5, 2.5),
                random.randint(3, 8), random.choice([True, False]), random.choice([True, False]), random.randint(0, 3),
                random.randint(0, 3), random.choice([True, False]), random.choice([True, False]), random.randint(0, 2),
                random.uniform(15, 40)
            ))
            mean_added += 1
        except:
            pass

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM range_signals_daily")
    range_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mean_reversion_signals_daily")
    mean_count = cur.fetchone()[0]

    print(f"\nRange signals: {range_count} total (added {range_added})")
    print(f"Mean reversion: {mean_count} total (added {mean_added})")

    conn.close()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
