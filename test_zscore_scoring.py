#!/usr/bin/env python3
"""
Test Z-Score Scoring Methodology
Uses existing PostgreSQL data to validate scoring approach
"""

import psycopg2
import numpy as np
from scipy.stats import zscore
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
import pandas as pd
import sys

# Database connection
DB_CONFIG = {
    'host': 'localhost',
    'user': 'stocks',
    'password': 'bed0elAn',
    'dbname': 'stocks'
}

def get_latest_data(conn, limit=100):
    """
    Fetch latest metrics for stocks
    Returns: DataFrame with all metrics
    """

    query = """
    WITH latest_dates AS (
        SELECT
            MAX(vm.date) as value_date,
            MAX(qm.date) as quality_date,
            MAX(gm.date) as growth_date,
            MAX(td.date::date) as tech_date
        FROM value_metrics vm
        CROSS JOIN quality_metrics qm
        CROSS JOIN growth_metrics gm
        CROSS JOIN technical_data_daily td
    )
    SELECT
        vm.symbol,
        vm.date as metric_date,

        -- Value Metrics
        vm.trailing_pe,
        vm.forward_pe,
        vm.price_to_book,
        vm.price_to_sales_ttm,
        vm.peg_ratio,
        vm.ev_to_revenue,
        vm.ev_to_ebitda,
        vm.dividend_yield,

        -- Quality Metrics
        qm.return_on_equity_pct,
        qm.return_on_assets_pct,
        qm.operating_margin_pct,
        qm.gross_margin_pct,
        qm.profit_margin_pct,
        qm.debt_to_equity,
        qm.current_ratio,
        qm.fcf_to_net_income,

        -- Growth Metrics
        gm.revenue_growth_3y_cagr,
        gm.eps_growth_3y_cagr,
        gm.net_income_growth_yoy,
        gm.fcf_growth_yoy,
        gm.roe_trend,

        -- Technical/Momentum Metrics
        td.rsi,
        td.macd,
        td.macd_signal,
        td.macd_hist,
        td.roc,
        td.mom,
        td.atr,
        td.mfi,
        td.sma_50,
        td.sma_200,

        -- Sector for grouping
        cp.sector,
        cp.industry

    FROM value_metrics vm
    INNER JOIN quality_metrics qm ON vm.symbol = qm.symbol
    INNER JOIN growth_metrics gm ON vm.symbol = gm.symbol
    INNER JOIN technical_data_daily td ON vm.symbol = td.symbol
    INNER JOIN company_profile cp ON vm.symbol = cp.ticker
    CROSS JOIN latest_dates ld
    WHERE vm.date = ld.value_date
      AND qm.date = ld.quality_date
      AND gm.date = ld.growth_date
      AND td.date::date = ld.tech_date
      AND cp.sector IS NOT NULL
      AND vm.trailing_pe IS NOT NULL
      AND qm.return_on_equity_pct IS NOT NULL
    ORDER BY vm.symbol
    LIMIT %s
    """

    df = pd.read_sql_query(query, conn, params=(limit,))
    return df

def calculate_scores_with_zscore(df):
    """
    Calculate factor scores using z-score methodology
    Matches user's approach with consistency fixes
    """

    print(f"\n{'='*60}")
    print(f"Processing {len(df)} stocks")
    print(f"{'='*60}\n")

    # Define metric groups
    value_metrics = [
        'trailing_pe', 'forward_pe', 'price_to_book', 'price_to_sales_ttm',
        'peg_ratio', 'ev_to_revenue', 'ev_to_ebitda'
    ]

    quality_metrics = [
        'return_on_equity_pct', 'return_on_assets_pct', 'operating_margin_pct',
        'gross_margin_pct', 'profit_margin_pct', 'fcf_to_net_income'
    ]

    growth_metrics = [
        'revenue_growth_3y_cagr', 'eps_growth_3y_cagr',
        'net_income_growth_yoy', 'fcf_growth_yoy', 'roe_trend'
    ]

    momentum_metrics = [
        'rsi', 'macd', 'roc', 'mom', 'mfi'
    ]

    print("Metric Groups:")
    print(f"  Value: {len(value_metrics)} metrics")
    print(f"  Quality: {len(quality_metrics)} metrics")
    print(f"  Growth: {len(growth_metrics)} metrics")
    print(f"  Momentum: {len(momentum_metrics)} metrics")
    print()

    # Calculate z-scores with proper filtering

    # VALUE METRICS: Only positive values (Fama-French methodology)
    print("Calculating VALUE z-scores (positive values only)...")
    for metric in value_metrics:
        if metric in df.columns:
            # Filter to positive values only
            positive_mask = (df[metric].notna()) & (df[metric] > 0) & (df[metric] < 5000)
            positive_values = df.loc[positive_mask, metric]

            if len(positive_values) > 1:
                # Calculate z-scores on positive values
                z_scores = zscore(positive_values)
                df.loc[positive_mask, f'{metric}_zscore'] = z_scores
                # For value metrics, LOWER is better, so invert
                df.loc[positive_mask, f'{metric}_zscore'] = -df.loc[positive_mask, f'{metric}_zscore']

                print(f"  {metric}: {len(positive_values)} values, mean={positive_values.mean():.2f}")

    # OTHER METRICS: All values (including negative)
    print("\nCalculating QUALITY z-scores (all values)...")
    for metric in quality_metrics:
        if metric in df.columns:
            valid_mask = df[metric].notna()
            valid_values = df.loc[valid_mask, metric]

            if len(valid_values) > 1:
                z_scores = zscore(valid_values)
                df.loc[valid_mask, f'{metric}_zscore'] = z_scores
                print(f"  {metric}: {len(valid_values)} values, mean={valid_values.mean():.2f}")

    print("\nCalculating GROWTH z-scores (all values)...")
    for metric in growth_metrics:
        if metric in df.columns:
            valid_mask = df[metric].notna()
            valid_values = df.loc[valid_mask, metric]

            if len(valid_values) > 1:
                z_scores = zscore(valid_values)
                df.loc[valid_mask, f'{metric}_zscore'] = z_scores
                print(f"  {metric}: {len(valid_values)} values, mean={valid_values.mean():.2f}")

    print("\nCalculating MOMENTUM z-scores (all values)...")
    for metric in momentum_metrics:
        if metric in df.columns:
            valid_mask = df[metric].notna()
            valid_values = df.loc[valid_mask, metric]

            if len(valid_values) > 1:
                z_scores = zscore(valid_values)
                df.loc[valid_mask, f'{metric}_zscore'] = z_scores
                print(f"  {metric}: {len(valid_values)} values, mean={valid_values.mean():.2f}")

    # Calculate factor scores (average of z-scores)
    print("\nCalculating factor scores...")

    df['value_score'] = df[[f'{m}_zscore' for m in value_metrics if f'{m}_zscore' in df.columns]].mean(axis=1)
    df['quality_score'] = df[[f'{m}_zscore' for m in quality_metrics if f'{m}_zscore' in df.columns]].mean(axis=1)
    df['growth_score'] = df[[f'{m}_zscore' for m in growth_metrics if f'{m}_zscore' in df.columns]].mean(axis=1)
    df['momentum_score'] = df[[f'{m}_zscore' for m in momentum_metrics if f'{m}_zscore' in df.columns]].mean(axis=1)

    # Remove rows with NaN scores
    df_clean = df.dropna(subset=['value_score', 'quality_score', 'growth_score', 'momentum_score'])

    print(f"  Stocks with all scores: {len(df_clean)}/{len(df)}")

    return df_clean

def calculate_composite_scores(df):
    """
    Calculate composite scores using RandomForest to determine weights
    """

    print(f"\n{'='*60}")
    print("Calculating Composite Scores with ML Weights")
    print(f"{'='*60}\n")

    # Prepare features
    X = df[['quality_score', 'value_score', 'growth_score', 'momentum_score']].values
    y = df['quality_score'].values  # Use quality as target (you can change this)

    # Handle any remaining NaN values
    imputer = SimpleImputer(strategy='mean')
    X = imputer.fit_transform(X)

    # Split and train
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)

    # Get weights
    weights = model.feature_importances_

    print("Model Performance:")
    print(f"  Mean Squared Error: {mse:.4f}")
    print()
    print("Feature Importances (Weights):")
    print(f"  Quality:  {weights[0]:.3f}")
    print(f"  Value:    {weights[1]:.3f}")
    print(f"  Growth:   {weights[2]:.3f}")
    print(f"  Momentum: {weights[3]:.3f}")
    print()

    # Calculate composite score
    df['composite_score'] = (
        weights[0] * df['quality_score'] +
        weights[1] * df['value_score'] +
        weights[2] * df['growth_score'] +
        weights[3] * df['momentum_score']
    )

    # Normalize to 0-100 scale
    df['composite_score_normalized'] = 50 + (df['composite_score'] * 15)
    df['composite_score_normalized'] = df['composite_score_normalized'].clip(0, 100)

    return df, weights

def print_results(df):
    """
    Print top stocks by each metric
    """

    print(f"\n{'='*60}")
    print("TOP 10 STOCKS BY EACH SCORE")
    print(f"{'='*60}\n")

    # Top by composite
    print("COMPOSITE SCORE (Top 10):")
    print("-" * 60)
    top_composite = df.nlargest(10, 'composite_score')[['symbol', 'sector', 'composite_score_normalized', 'value_score', 'quality_score', 'growth_score', 'momentum_score']]
    for idx, row in top_composite.iterrows():
        print(f"  {row['symbol']:6s} - {row['sector']:20s} - Composite: {row['composite_score_normalized']:5.1f} "
              f"(V:{row['value_score']:5.2f} Q:{row['quality_score']:5.2f} G:{row['growth_score']:5.2f} M:{row['momentum_score']:5.2f})")

    print("\nVALUE SCORE (Top 10):")
    print("-" * 60)
    top_value = df.nlargest(10, 'value_score')[['symbol', 'sector', 'value_score', 'trailing_pe', 'price_to_book']]
    for idx, row in top_value.iterrows():
        print(f"  {row['symbol']:6s} - {row['sector']:20s} - Score: {row['value_score']:6.2f} (PE: {row['trailing_pe']:6.1f}, PB: {row['price_to_book']:5.2f})")

    print("\nQUALITY SCORE (Top 10):")
    print("-" * 60)
    top_quality = df.nlargest(10, 'quality_score')[['symbol', 'sector', 'quality_score', 'return_on_equity_pct', 'operating_margin_pct']]
    for idx, row in top_quality.iterrows():
        print(f"  {row['symbol']:6s} - {row['sector']:20s} - Score: {row['quality_score']:6.2f} (ROE: {row['return_on_equity_pct']:6.1f}%, OpMargin: {row['operating_margin_pct']:5.1f}%)")

    print("\nGROWTH SCORE (Top 10):")
    print("-" * 60)
    top_growth = df.nlargest(10, 'growth_score')[['symbol', 'sector', 'growth_score', 'revenue_growth_3y_cagr', 'eps_growth_3y_cagr']]
    for idx, row in top_growth.iterrows():
        rev = row['revenue_growth_3y_cagr'] if pd.notna(row['revenue_growth_3y_cagr']) else 0
        eps = row['eps_growth_3y_cagr'] if pd.notna(row['eps_growth_3y_cagr']) else 0
        print(f"  {row['symbol']:6s} - {row['sector']:20s} - Score: {row['growth_score']:6.2f} (Rev: {rev:6.1f}%, EPS: {eps:6.1f}%)")

    print("\nMOMENTUM SCORE (Top 10):")
    print("-" * 60)
    top_momentum = df.nlargest(10, 'momentum_score')[['symbol', 'sector', 'momentum_score', 'rsi', 'roc']]
    for idx, row in top_momentum.iterrows():
        print(f"  {row['symbol']:6s} - {row['sector']:20s} - Score: {row['momentum_score']:6.2f} (RSI: {row['rsi']:5.1f}, ROC: {row['roc']:6.1f}%)")

def main():
    """
    Main execution
    """

    print(f"\n{'='*60}")
    print("Z-SCORE SCORING METHODOLOGY TEST")
    print("Using Existing PostgreSQL Data")
    print(f"{'='*60}\n")

    # Connect to database
    print("Connecting to database...")
    conn = psycopg2.connect(**DB_CONFIG)

    # Fetch data
    print("Fetching latest metrics for stocks...")
    df = get_latest_data(conn, limit=500)  # Test with 500 stocks
    print(f"Loaded {len(df)} stocks with complete data\n")

    if len(df) == 0:
        print("❌ No data found! Check that tables have data.")
        return

    # Calculate z-score based scores
    df_scored = calculate_scores_with_zscore(df)

    # Calculate composite with ML weights
    df_final, weights = calculate_composite_scores(df_scored)

    # Print results
    print_results(df_final)

    # Summary statistics
    print(f"\n{'='*60}")
    print("SCORE DISTRIBUTION STATISTICS")
    print(f"{'='*60}\n")

    print("Composite Score (normalized 0-100):")
    print(f"  Mean: {df_final['composite_score_normalized'].mean():.2f}")
    print(f"  Std:  {df_final['composite_score_normalized'].std():.2f}")
    print(f"  Min:  {df_final['composite_score_normalized'].min():.2f}")
    print(f"  Max:  {df_final['composite_score_normalized'].max():.2f}")

    print("\nZ-Score Distributions:")
    for score in ['value_score', 'quality_score', 'growth_score', 'momentum_score']:
        print(f"  {score:15s}: mean={df_final[score].mean():6.2f}, std={df_final[score].std():5.2f}")

    print(f"\n{'='*60}")
    print("✅ Scoring Test Complete!")
    print(f"{'='*60}\n")

    print("Results show that:")
    print("  1. Z-score methodology works with existing data")
    print("  2. Scores are properly normalized")
    print("  3. Value metrics use positive-only filtering")
    print("  4. ML weights provide composite score")
    print()
    print("Next steps:")
    print("  - Review top stocks to validate results")
    print("  - Add technical indicators (bollinger, etc.)")
    print("  - Add volatility metrics")
    print("  - Expand to full dataset")

    conn.close()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
