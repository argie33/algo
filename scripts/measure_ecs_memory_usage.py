#!/usr/bin/env python3
"""
Measure actual ECS task memory usage to inform right-sizing decisions (Phase 6).

This script polls CloudWatch for actual memory utilization of each loader task
over the past 7 days, helping identify which loaders can be safely right-sized.

Run daily: python3 scripts/measure_ecs_memory_usage.py
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List

import boto3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

# All loaders with their current allocations
LOADERS = {
    # Lightweight (256/512)
    'market_exposure_daily': {'cpu': 256, 'memory': 512},
    'dxy_index': {'cpu': 256, 'memory': 512},
    'market_constituents': {'cpu': 256, 'memory': 512},
    'market_health_daily': {'cpu': 256, 'memory': 512},
    'market_sentiment': {'cpu': 256, 'memory': 512},

    # Medium (512/1024)
    'growth_metrics': {'cpu': 512, 'memory': 1024},
    'quality_metrics': {'cpu': 512, 'memory': 1024},
    'value_metrics': {'cpu': 512, 'memory': 1024},
    'positioning_metrics': {'cpu': 512, 'memory': 1024},
    'stability_metrics': {'cpu': 512, 'memory': 1024},
    'momentum_metrics': {'cpu': 512, 'memory': 1024},
    'stock_prices_daily': {'cpu': 512, 'memory': 1024},
    'sector_ranking': {'cpu': 512, 'memory': 1024},
    'industry_ranking': {'cpu': 512, 'memory': 1024},
    'earnings_history': {'cpu': 512, 'memory': 1024},
    'earnings_calendar': {'cpu': 512, 'memory': 1024},
    'compute_performance_metrics': {'cpu': 512, 'memory': 1024},
    'financials_annual_income': {'cpu': 512, 'memory': 1024},
    'financials_annual_balance': {'cpu': 512, 'memory': 1024},
    'financials_annual_cashflow': {'cpu': 512, 'memory': 1024},
    'financials_quarterly_income': {'cpu': 512, 'memory': 1024},
    'financials_quarterly_balance': {'cpu': 512, 'memory': 1024},
    'financials_quarterly_cashflow': {'cpu': 512, 'memory': 1024},
    'financials_ttm_income': {'cpu': 512, 'memory': 1024},
    'financials_ttm_cashflow': {'cpu': 512, 'memory': 1024},

    # Heavy (1024/2048)
    'technical_data_daily': {'cpu': 1024, 'memory': 2048},
    'trend_template_data': {'cpu': 1024, 'memory': 2048},
    'yfinance_snapshot': {'cpu': 1024, 'memory': 2048},
    'algo_metrics_daily': {'cpu': 1024, 'memory': 2048},
    'buy_sell_daily': {'cpu': 1024, 'memory': 2048},
    'company_profile': {'cpu': 1024, 'memory': 2048},
    'analyst_sentiment': {'cpu': 1024, 'memory': 2048},
    'analyst_upgrades_downgrades': {'cpu': 1024, 'memory': 2048},
    'stock_scores': {'cpu': 1024, 'memory': 2048},
}


def get_memory_stats(loader_name: str) -> Dict:
    """Query CloudWatch for memory usage stats over past 7 days."""
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace='ECS/ContainerInsights',
            MetricName='ContainerMemoryUtilized',
            Dimensions=[
                {
                    'Name': 'TaskDefinitionFamily',
                    'Value': f'algo-{loader_name}'
                }
            ],
            StartTime=datetime.utcnow() - timedelta(days=7),
            EndTime=datetime.utcnow(),
            Period=3600,  # 1-hour aggregation
            Statistics=['Average', 'Maximum'],
            Unit='Bytes'
        )

        if not response['Datapoints']:
            return {
                'loader': loader_name,
                'allocated_mb': LOADERS[loader_name]['memory'],
                'max_used_mb': None,
                'avg_used_mb': None,
                'utilization_pct': None,
                'status': 'NO_DATA'
            }

        max_bytes = max([dp['Maximum'] for dp in response['Datapoints']])
        avg_bytes = sum([dp['Average'] for dp in response['Datapoints']]) / len(response['Datapoints'])

        allocated_mb = LOADERS[loader_name]['memory']
        max_mb = max_bytes / (1024 * 1024)
        avg_mb = avg_bytes / (1024 * 1024)
        utilization_pct = (max_mb / allocated_mb) * 100

        return {
            'loader': loader_name,
            'allocated_mb': allocated_mb,
            'max_used_mb': round(max_mb, 1),
            'avg_used_mb': round(avg_mb, 1),
            'utilization_pct': round(utilization_pct, 1),
            'status': 'OK'
        }
    except Exception as e:
        logger.warning(f"Failed to get metrics for {loader_name}: {e}")
        return {
            'loader': loader_name,
            'allocated_mb': LOADERS[loader_name]['memory'],
            'max_used_mb': None,
            'avg_used_mb': None,
            'utilization_pct': None,
            'status': f'ERROR: {str(e)[:50]}'
        }


def main():
    logger.info("=" * 100)
    logger.info("ECS TASK MEMORY UTILIZATION REPORT (Last 7 Days)")
    logger.info("=" * 100)

    results = []
    for loader_name in sorted(LOADERS.keys()):
        stats = get_memory_stats(loader_name)
        results.append(stats)

    # Sort by utilization percentage (highest first)
    results_by_usage = sorted(
        [r for r in results if r['utilization_pct'] is not None],
        key=lambda x: x['utilization_pct'],
        reverse=True
    )

    # Print results grouped by allocation size
    logger.info("\nHEAVY LOADERS (1024 CPU / 2048 MB allocated):")
    logger.info("-" * 100)
    for r in results_by_usage:
        if r['allocated_mb'] == 2048:
            status_icon = '✓' if r['utilization_pct'] < 50 else '⚠' if r['utilization_pct'] < 75 else '❌'
            logger.info(
                f"{status_icon} {r['loader']:30} | "
                f"Allocated: {r['allocated_mb']:5} MB | "
                f"Max: {r['max_used_mb']:6} MB ({r['utilization_pct']:5.1f}%) | "
                f"Avg: {r['avg_used_mb']:6} MB"
            )

    logger.info("\nMEDIUM LOADERS (512 CPU / 1024 MB allocated):")
    logger.info("-" * 100)
    for r in results_by_usage:
        if r['allocated_mb'] == 1024:
            status_icon = '✓' if r['utilization_pct'] < 50 else '⚠' if r['utilization_pct'] < 75 else '❌'
            logger.info(
                f"{status_icon} {r['loader']:30} | "
                f"Allocated: {r['allocated_mb']:5} MB | "
                f"Max: {r['max_used_mb']:6} MB ({r['utilization_pct']:5.1f}%) | "
                f"Avg: {r['avg_used_mb']:6} MB"
            )

    logger.info("\nLIGHTWEIGHT LOADERS (256 CPU / 512 MB allocated):")
    logger.info("-" * 100)
    for r in results_by_usage:
        if r['allocated_mb'] == 512:
            status_icon = '✓' if r['utilization_pct'] < 50 else '⚠' if r['utilization_pct'] < 75 else '❌'
            logger.info(
                f"{status_icon} {r['loader']:30} | "
                f"Allocated: {r['allocated_mb']:5} MB | "
                f"Max: {r['max_used_mb']:6} MB ({r['utilization_pct']:5.1f}%) | "
                f"Avg: {r['avg_used_mb']:6} MB"
            )

    # Summary and recommendations
    no_data = [r for r in results if r['status'] != 'OK']
    underutilized = [r for r in results_by_usage if r['utilization_pct'] < 50]
    overutilized = [r for r in results_by_usage if r['utilization_pct'] > 80]

    logger.info("\n" + "=" * 100)
    logger.info("SUMMARY & RECOMMENDATIONS")
    logger.info("=" * 100)
    logger.info(f"\nTotal loaders analyzed: {len(LOADERS)}")
    logger.info(f"  ✓ With data: {len(results_by_usage)}")
    logger.info(f"  ⚠ Without data: {len(no_data)}")

    if underutilized:
        logger.info(f"\nUnderutilized loaders (< 50% memory usage): {len(underutilized)}")
        for r in underutilized:
            suggested_reduction = {
                2048: 1536,
                1024: 768,
                512: 256
            }.get(r['allocated_mb'])
            logger.info(
                f"  → {r['loader']:30} "
                f"can reduce {r['allocated_mb']} MB → {suggested_reduction} MB "
                f"(currently using {r['max_used_mb']} MB max)"
            )

    if overutilized:
        logger.info(f"\nOverutilized loaders (> 80% memory usage): {len(overutilized)}")
        for r in overutilized:
            logger.info(
                f"  ⚠ {r['loader']:30} "
                f"is close to limit ({r['utilization_pct']:.1f}% of {r['allocated_mb']} MB) — DO NOT REDUCE"
            )

    logger.info("\nNext steps:")
    logger.info("1. Run this script daily for 7 days to collect baseline data")
    logger.info("2. After 7 days, identify consistently underutilized loaders")
    logger.info("3. Update terraform/modules/loaders/main.tf with safe reductions (Phase 6)")
    logger.info("4. See scripts/ecs_rightsizing_strategy.md for detailed guidance")

    logger.info("\n" + "=" * 100)


if __name__ == '__main__':
    main()
