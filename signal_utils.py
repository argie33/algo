#!/usr/bin/env python3
"""
Shared Signal Calculation Utilities

Extracted from loadbuyselldaily.py for reuse by:
- loadrangesignals.py
- loadmeanreversionsignals.py

Provides common technical indicator and signal quality calculations
that all three strategies need for complete data parity.
"""

import pandas as pd
import numpy as np
import logging

###############################################################################
# 1) TECHNICAL INDICATOR CALCULATIONS
###############################################################################

def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index"""
    try:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        logging.warning(f"RSI calculation error: {e}")
        return pd.Series([None] * len(prices), index=prices.index)

def calculate_atr(high, low, close, period=14):
    """Calculate Average True Range"""
    try:
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr
    except Exception as e:
        logging.warning(f"ATR calculation error: {e}")
        return pd.Series([None] * len(high), index=high.index)

def calculate_adx(high, low, close, period=14):
    """Calculate Average Directional Index (simplified)"""
    try:
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_val = tr.rolling(window=period).mean()

        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_val)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_val)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        return adx
    except Exception as e:
        logging.warning(f"ADX calculation error: {e}")
        return pd.Series([None] * len(high), index=high.index)

def calculate_sma(prices, period):
    """Calculate Simple Moving Average"""
    try:
        return prices.rolling(window=period).mean()
    except Exception as e:
        logging.warning(f"SMA calculation error: {e}")
        return pd.Series([None] * len(prices), index=prices.index)

def calculate_ema(prices, period):
    """Calculate Exponential Moving Average"""
    try:
        return prices.ewm(span=period, adjust=False).mean()
    except Exception as e:
        logging.warning(f"EMA calculation error: {e}")
        return pd.Series([None] * len(prices), index=prices.index)

def calculate_macd(close, fast=12, slow=26, signal=9):
    """Calculate MACD and signal line"""
    try:
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        return macd, macd_signal
    except Exception as e:
        logging.warning(f"MACD calculation error: {e}")
        return pd.Series([None] * len(close)), pd.Series([None] * len(close))

###############################################################################
# 2) MOVING AVERAGES & PRICE POSITION
###############################################################################

def compute_moving_averages(df):
    """Add SMA 20/50/200 and EMA 21/26 to dataframe"""
    try:
        df['sma_20'] = calculate_sma(df['close'], 20)
        df['sma_50'] = calculate_sma(df['close'], 50)
        df['sma_200'] = calculate_sma(df['close'], 200)
        df['ema_21'] = calculate_ema(df['close'], 21)
        df['ema_26'] = calculate_ema(df['close'], 26)
        return df
    except Exception as e:
        logging.warning(f"compute_moving_averages error: {e}")
        return df

def compute_relative_position(df):
    """Calculate percentage from key moving averages"""
    try:
        df['pct_from_ema21'] = df.apply(
            lambda row: round(((row['close'] - row.get('ema_21', 0)) / row.get('ema_21', 1) * 100), 2)
            if pd.notna(row.get('ema_21')) and row.get('ema_21') > 0 else None,
            axis=1
        )
        df['pct_from_sma50'] = df.apply(
            lambda row: round(((row['close'] - row.get('sma_50', 0)) / row.get('sma_50', 1) * 100), 2)
            if pd.notna(row.get('sma_50')) and row.get('sma_50') > 0 else None,
            axis=1
        )
        df['pct_from_sma200'] = df.apply(
            lambda row: round(((row['close'] - row.get('sma_200', 0)) / row.get('sma_200', 1) * 100), 2)
            if pd.notna(row.get('sma_200')) and row.get('sma_200') > 0 else None,
            axis=1
        )
        return df
    except Exception as e:
        logging.warning(f"compute_relative_position error: {e}")
        return df

###############################################################################
# 3) VOLUME ANALYSIS
###############################################################################

def compute_volume_analysis(df):
    """Calculate volume metrics: 50-day average, surge %, ratio"""
    try:
        # 50-day rolling average volume
        df['avg_volume_50d'] = df['volume'].rolling(window=50).mean()

        # Volume surge percentage
        df['volume_surge_pct'] = df.apply(
            lambda row: round(((row['volume'] / row['avg_volume_50d'] - 1) * 100), 2)
            if pd.notna(row.get('avg_volume_50d')) and row['avg_volume_50d'] > 0 else None,
            axis=1
        )

        # Volume ratio
        df['volume_ratio'] = df.apply(
            lambda row: round(row['volume'] / row['avg_volume_50d'], 2)
            if pd.notna(row.get('avg_volume_50d')) and row['avg_volume_50d'] > 0 else None,
            axis=1
        )

        return df
    except Exception as e:
        logging.warning(f"compute_volume_analysis error: {e}")
        return df

###############################################################################
# 4) RS RATING & MANSFIELD RS
###############################################################################

def compute_rs_metrics(df):
    """Calculate RS rating and Mansfield RS"""
    try:
        # RS Rating (0-99): Performance vs 200-day high
        df['rs_rating'] = None
        for i in range(200, len(df)):
            if i >= 200:
                window = df.iloc[i-200:i+1]
                current_price = window.iloc[-1]['close']
                high_200d = window['high'].max()

                if high_200d > 0 and pd.notna(current_price):
                    rs = (current_price / high_200d) * 100
                    if pd.notna(rs):
                        df.at[i, 'rs_rating'] = min(99, max(1, int(rs)))

        # Mansfield RS: Current price vs 52-week high
        high_52w = df['high'].rolling(window=252).max()
        df['mansfield_rs'] = (df['close'] / high_52w * 100).round(2)
        df.loc[(high_52w.isna()) | (high_52w <= 0) | (df['close'].isna()), 'mansfield_rs'] = None

        return df
    except Exception as e:
        logging.warning(f"compute_rs_metrics error: {e}")
        return df

###############################################################################
# 5) DAILY RANGE & BASE ANALYSIS
###############################################################################

def compute_daily_range_pct(df):
    """Calculate daily range percentage"""
    try:
        df['daily_range_pct'] = ((df['high'] - df['low']) / df['close']) * 100
        return df
    except Exception as e:
        logging.warning(f"compute_daily_range_pct error: {e}")
        return df

def compute_base_analysis(df):
    """Identify base type and length"""
    try:
        # Base type based on daily range
        df['base_type'] = df['daily_range_pct'].apply(
            lambda x: 'TIGHT_RANGE' if x < 1.0 else ('NORMAL_RANGE' if x < 2.5 else 'WIDE_RANGE')
            if pd.notna(x) else None
        )

        # Base length: count consecutive consolidation days
        df['base_length_days'] = None
        for i in range(1, len(df)):
            length = 0
            for j in range(i - 1, max(-1, i - 21), -1):
                if df.iloc[j]['base_type'] in ['TIGHT_RANGE', 'NORMAL_RANGE']:
                    length += 1
                else:
                    break
            if length > 0:
                df.at[i, 'base_length_days'] = length

        return df
    except Exception as e:
        logging.warning(f"compute_base_analysis error: {e}")
        return df

###############################################################################
# 6) MARKET STAGE DETECTION
###############################################################################

def detect_market_stage(df):
    """Detect Stan Weinstein 4-stage market pattern"""
    try:
        df['market_stage'] = None
        df['stage_number'] = None
        df['stage_confidence'] = None
        df['substage'] = None

        for i in range(200, len(df)):
            if i >= 200:
                window = df.iloc[i-200:i+1]
                close = window.iloc[-1]['close']
                sma_50 = df.iloc[i].get('sma_50')
                sma_200 = df.iloc[i].get('sma_200')

                # Simplified 4-stage detection
                if pd.notna(sma_50) and pd.notna(sma_200):
                    if close > sma_50 > sma_200:
                        df.at[i, 'market_stage'] = 'Stage 2 - Advancing'
                        df.at[i, 'stage_number'] = 2
                        df.at[i, 'stage_confidence'] = 0.8
                    elif close > sma_200 and close < sma_50:
                        df.at[i, 'market_stage'] = 'Stage 1 - Basing'
                        df.at[i, 'stage_number'] = 1
                        df.at[i, 'stage_confidence'] = 0.7
                    elif close < sma_50 < sma_200:
                        df.at[i, 'market_stage'] = 'Stage 4 - Declining'
                        df.at[i, 'stage_number'] = 4
                        df.at[i, 'stage_confidence'] = 0.8
                    else:
                        df.at[i, 'market_stage'] = 'Stage 3 - Topping'
                        df.at[i, 'stage_number'] = 3
                        df.at[i, 'stage_confidence'] = 0.7

        return df
    except Exception as e:
        logging.warning(f"detect_market_stage error: {e}")
        return df

###############################################################################
# 7) SIGNAL STRENGTH & QUALITY
###############################################################################

def compute_signal_strength(df):
    """Calculate signal strength score (0-100)"""
    try:
        strengths = []
        for i in range(len(df)):
            row = df.iloc[i]

            # Skip if no signal
            if row.get('signal') not in ['BUY', 'SELL', 'Buy', 'Sell']:
                strengths.append(None)
                continue

            strength = 0.0

            # RSI contribution (30%)
            rsi = row.get('rsi')
            if pd.notna(rsi):
                if row.get('signal') == 'BUY' and rsi < 70:
                    strength += min(30, rsi / 70 * 30)
                elif row.get('signal') == 'SELL' and rsi > 30:
                    strength += min(30, (100 - rsi) / 70 * 30)

            # Volume (25%)
            vol_surge = row.get('volume_surge_pct')
            if pd.notna(vol_surge):
                strength += min(25, max(0, vol_surge / 100 * 25))

            # Price action (25%)
            if pd.notna(row.get('high')) and pd.notna(row.get('low')):
                daily_range = row.get('high') - row.get('low')
                if daily_range > 0:
                    close_pos = (row.get('close') - row.get('low')) / daily_range
                    if row.get('signal') == 'BUY':
                        strength += min(25, close_pos * 25)
                    else:
                        strength += min(25, (1 - close_pos) * 25)

            # ADX trend (20%)
            adx = row.get('adx')
            if pd.notna(adx):
                strength += min(20, max(0, adx / 40 * 20))

            strengths.append(min(100, strength))

        df['signal_strength'] = strengths
        return df
    except Exception as e:
        logging.warning(f"compute_signal_strength error: {e}")
        return df

def compute_entry_quality(df):
    """Calculate entry quality score (0-100)"""
    try:
        scores = []
        for _, row in df.iterrows():
            score = 0

            # Breakout quality (0-40)
            if pd.notna(row.get('daily_range_pct')):
                if row.get('daily_range_pct') > 3.0:
                    score += 40
                elif row.get('daily_range_pct') > 1.5:
                    score += 20

            # Volume (0-30)
            vol_surge = row.get('volume_surge_pct')
            if pd.notna(vol_surge):
                if vol_surge > 50:
                    score += 30
                elif vol_surge > 25:
                    score += 15

            # RS Rating (0-20)
            rs = row.get('rs_rating')
            if pd.notna(rs):
                if rs > 75:
                    score += 20
                elif rs > 50:
                    score += 10

            # Price position (0-10)
            if pd.notna(row.get('close')) and pd.notna(row.get('sma_50')):
                if row.get('close') > row.get('sma_50'):
                    score += 10

            scores.append(min(100, score) if score > 0 else None)

        df['entry_quality_score'] = scores
        return df
    except Exception as e:
        logging.warning(f"compute_entry_quality error: {e}")
        return df

###############################################################################
# 8) BREAKOUT QUALITY
###############################################################################

def compute_breakout_quality(df):
    """Rate breakout quality: STRONG, MODERATE, WEAK"""
    try:
        qualities = []
        for _, row in df.iterrows():
            daily_range = row.get('daily_range_pct')
            vol_surge = row.get('volume_surge_pct')

            if pd.isna(daily_range) or pd.isna(vol_surge):
                qualities.append(None)
                continue

            if daily_range > 3.0 and vol_surge > 50:
                qualities.append('STRONG')
            elif daily_range > 1.5 and vol_surge > 25:
                qualities.append('MODERATE')
            else:
                qualities.append('WEAK')

        df['breakout_quality'] = qualities
        return df
    except Exception as e:
        logging.warning(f"compute_breakout_quality error: {e}")
        return df

###############################################################################
# 9) POSITION SIZING & PROFIT TARGETS
###############################################################################

def compute_position_sizing(df):
    """Calculate position size recommendation"""
    try:
        df['position_size_recommendation'] = df.apply(
            lambda row: max(0.5, min(5.0, 1.0 / (row.get('risk_pct', 2.0) / 100)))
            if pd.notna(row.get('risk_pct')) else None,
            axis=1
        )
        return df
    except Exception as e:
        logging.warning(f"compute_position_sizing error: {e}")
        return df

def compute_profit_targets(df, entry_col='buy_level'):
    """Calculate profit targets"""
    try:
        entry_price = df.get(entry_col, df.get('close', 0))
        df['profit_target_8pct'] = entry_price * 1.08
        df['profit_target_20pct'] = entry_price * 1.20
        df['profit_target_25pct'] = entry_price * 1.25
        return df
    except Exception as e:
        logging.warning(f"compute_profit_targets error: {e}")
        return df

def compute_exit_triggers(df, entry_col='buy_level', stop_col='stop_level'):
    """Calculate exit trigger prices"""
    try:
        entry = df.get(entry_col, df.get('close', 0))
        stop = df.get(stop_col, 0)

        df['exit_trigger_1_price'] = entry * 1.08
        df['exit_trigger_2_price'] = entry * 1.20
        df['exit_trigger_3_price'] = entry * 1.25
        df['exit_trigger_4_price'] = stop
        return df
    except Exception as e:
        logging.warning(f"compute_exit_triggers error: {e}")
        return df

###############################################################################
# 10) SATA SCORE (Stage Analysis Technical Attributes)
###############################################################################

def calculate_sata(row):
    """Calculate SATA score (0-10 scale)"""
    try:
        stage_num = row.get('stage_number')
        rs_rating_val = row.get('rs_rating')
        vol_surge = row.get('volume_surge_pct')
        strength_val = row.get('signal_strength')

        if stage_num is None or pd.isna(stage_num):
            return None

        sata = float(stage_num)

        if rs_rating_val is not None and not pd.isna(rs_rating_val):
            rs_bonus = min(3.0, (float(rs_rating_val) / 99.0) * 3.0)
            sata += rs_bonus

        if vol_surge is not None and not pd.isna(vol_surge):
            vol_bonus = min(2.0, (float(vol_surge) / 100.0) * 2.0)
            sata += vol_bonus

        if strength_val is not None and not pd.isna(strength_val):
            strength_bonus = min(1.0, (float(strength_val) / 100.0) * 1.0)
            sata += strength_bonus

        return max(0, min(10, int(round(sata))))
    except Exception as e:
        logging.warning(f"SATA calculation error: {e}")
        return None

def compute_sata_scores(df):
    """Add SATA scores to dataframe"""
    try:
        df['sata_score'] = df.apply(calculate_sata, axis=1)
        return df
    except Exception as e:
        logging.warning(f"compute_sata_scores error: {e}")
        return df
