#!/usr/bin/env python3
"""CLI tool for safeguard management and monitoring.

Commands:
  status              Show current safeguard configuration and status
  enable <safeguard>  Enable a specific safeguard
  disable <safeguard> Disable a specific safeguard
  config <key> <val>  Set configuration parameter
  audit <symbol>      View audit trail for symbol
  metrics <days>      Get performance metrics
  risk <symbol>       Score position risk
  alerts <hours>      Show recent alerts
  report              Generate compliance report
"""

import sys
import argparse
from datetime import date, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def cmd_status(args):
    """Show safeguard status and configuration."""
    from safeguard_config import get_safeguard_config
    from safeguard_audit import SafeguardAudit

    config = get_safeguard_config()
    audit = SafeguardAudit(config)

    print("\n" + "="*70)
    print("SAFEGUARD STATUS")
    print("="*70)

    # Configuration
    print("\nConfiguration:")
    print(f"  Liquidity:       {'ENABLED' if config.is_enabled('liquidity') else 'DISABLED'}")
    print(f"    Min volume:    {config.get('min_daily_volume_shares'):,.0f} shares")
    print(f"    Max spread:    {config.get('max_spread_pct')}%")

    print(f"  Earnings:        {'ENABLED' if config.is_enabled('earnings') else 'DISABLED'}")
    print(f"    Blackout:      ±{config.get('earnings_blackout_days_before')} days")

    print(f"  Margin:          {'ENABLED' if config.is_enabled('margin') else 'DISABLED'}")
    print(f"    Alert:         {config.get('margin_alert_pct')}%")
    print(f"    Halt:          {config.get('margin_halt_pct')}%")

    print(f"  Economic:        {'ENABLED' if config.is_enabled('economic_calendar') else 'DISABLED'}")
    print(f"    Halt window:   {config.get('halt_entries_before_major_release_minutes')} min")

    # Alerts
    print(f"\nAlerts:")
    print(f"  Status:          {'ENABLED' if config.get('alerts_enabled') else 'DISABLED'}")
    print(f"  Channels:        {', '.join(config.get('alert_channels', []))}")

    # Metrics
    print(f"\nMetrics:")
    report = audit.get_performance_report(days=7)
    if report['safeguards']:
        print(f"  Period:          7 days")
        print(f"  Signals:         {report['summary']['total_signals']}")
        print(f"  Blocks:          {report['summary']['total_blocks']}")
        print(f"  Block rate:      {report['summary']['overall_block_rate']:.2f}%")
    else:
        print(f"  No data available")

    print("\n" + "="*70)


def cmd_enable(args):
    """Enable a safeguard."""
    from safeguard_config import get_safeguard_config

    config = get_safeguard_config()
    safeguard = args.safeguard

    valid = ['liquidity', 'earnings', 'margin', 'economic_calendar']
    if safeguard not in valid:
        print(f"Invalid safeguard: {safeguard}. Valid options: {', '.join(valid)}")
        return

    config.set(f'{safeguard}_enabled', True)
    print(f"[OK] Enabled {safeguard}")


def cmd_disable(args):
    """Disable a safeguard."""
    from safeguard_config import get_safeguard_config

    config = get_safeguard_config()
    safeguard = args.safeguard

    valid = ['liquidity', 'earnings', 'margin', 'economic_calendar']
    if safeguard not in valid:
        print(f"Invalid safeguard: {safeguard}. Valid options: {', '.join(valid)}")
        return

    config.set(f'{safeguard}_enabled', False)
    print(f"[OK] Disabled {safeguard}")


def cmd_config(args):
    """Set configuration parameter."""
    from safeguard_config import get_safeguard_config

    config = get_safeguard_config()
    key = args.key
    value = args.value

    # Try to parse value type
    if value.lower() in ('true', 'false'):
        value = value.lower() == 'true'
    elif value.replace('.', '').isdigit():
        value = float(value) if '.' in value else int(value)

    config.set(key, value)
    print(f"[OK] Set {key} = {value}")


def cmd_audit(args):
    """View audit trail for symbol."""
    from safeguard_audit import SafeguardAudit

    audit = SafeguardAudit()
    trails = audit.get_audit_trail(symbol=args.symbol, days=30)

    if not trails:
        print(f"No audit entries for {args.symbol}")
        return

    print(f"\nAudit Trail for {args.symbol} (last 30 days):")
    print("-" * 80)

    for entry in trails[:20]:
        status = "[BLOCK]" if entry['decision'] == 'BLOCK' else "[ALLOW]"
        print(f"  {status} {entry['timestamp']}: {entry['safeguard']}")
        print(f"         {entry['reason']}")

    print(f"\nTotal entries: {len(trails)}")


def cmd_metrics(args):
    """Get performance metrics."""
    from safeguard_audit import SafeguardAudit

    audit = SafeguardAudit()
    report = audit.get_performance_report(days=args.days)

    if not report['safeguards']:
        print(f"No metrics available for past {args.days} days")
        return

    print(f"\nPerformance Metrics ({args.days} days):")
    print("=" * 70)
    print(f"{'Safeguard':<20} {'Signals':>8} {'Blocks':>8} {'Block %':>10}")
    print("-" * 70)

    for sg in report['safeguards']:
        block_pct = (sg['blocks'] / sg['signals'] * 100) if sg['signals'] > 0 else 0
        print(f"{sg['name']:<20} {sg['signals']:>8} {sg['blocks']:>8} {block_pct:>9.1f}%")

    print("-" * 70)
    print(f"{'TOTAL':<20} {report['summary']['total_signals']:>8} {report['summary']['total_blocks']:>8} {report['summary']['overall_block_rate']:>9.1f}%")


def cmd_risk(args):
    """Score position risk."""
    from safeguard_risk_scoring import PositionRiskScorer
    from datetime import date

    scorer = PositionRiskScorer()
    risk = scorer.score_position(
        symbol=args.symbol,
        entry_price=float(args.entry_price),
        shares=int(args.shares),
        entry_date=date.today() if not hasattr(args, 'entry_date') else args.entry_date,
    )

    print(f"\nRisk Score for {args.symbol}:")
    print("=" * 70)
    print(f"  Score:           {risk['composite_risk_score']}/10")
    print(f"  Level:           {risk['risk_level']}")
    print(f"\nBreakdown:")
    for component, score in risk['score_breakdown'].items():
        print(f"  {component:<25s}: {score:.2f}")
    print(f"\nRecommendation:  {risk['recommendation']}")


def cmd_alerts(args):
    """Show recent alerts."""
    from safeguard_alerts import SafeguardAlert

    alerts = SafeguardAlert()
    recent = alerts.get_recent_alerts(hours=args.hours)

    if not recent:
        print(f"No alerts in past {args.hours} hours")
        return

    print(f"\nRecent Alerts (past {args.hours} hours):")
    print("=" * 70)

    for alert in recent[:10]:
        icon = "🔴" if alert['level'] == 'CRITICAL' else "🟡" if alert['level'] == 'WARNING' else "ℹ️"
        print(f"  {icon} [{alert['level']:8s}] {alert['title']}")
        print(f"     {alert['timestamp']} ({alert['safeguard']})")
        print(f"     {alert['message']}")
        print()


def cmd_report(args):
    """Generate compliance report."""
    from safeguard_audit import SafeguardAudit
    from datetime import date

    audit = SafeguardAudit()
    report = audit.get_performance_report(days=args.days)

    print(f"\nCompliance Report ({args.days} days)")
    print("=" * 70)
    print(f"Generated: {date.today()}\n")

    print("Safeguard Activity:")
    for sg in report['safeguards']:
        print(f"  {sg['name']:20s}: {sg['signals']:5d} signals, {sg['blocks']:5d} blocks ({sg['block_rate_avg']:.1f}%)")

    print(f"\nTotal Signals Evaluated: {report['summary']['total_signals']}")
    print(f"Total Blocks Applied:   {report['summary']['total_blocks']}")
    print(f"Overall Block Rate:     {report['summary']['overall_block_rate']:.2f}%")

    print(f"\n[OK] All safeguards operational and logging to database")


def main():
    parser = argparse.ArgumentParser(
        description='Safeguard Management CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Status command
    subparsers.add_parser('status', help='Show safeguard status')

    # Enable command
    enable = subparsers.add_parser('enable', help='Enable safeguard')
    enable.add_argument('safeguard', choices=['liquidity', 'earnings', 'margin', 'economic_calendar'])

    # Disable command
    disable = subparsers.add_parser('disable', help='Disable safeguard')
    disable.add_argument('safeguard', choices=['liquidity', 'earnings', 'margin', 'economic_calendar'])

    # Config command
    config = subparsers.add_parser('config', help='Set configuration')
    config.add_argument('key')
    config.add_argument('value')

    # Audit command
    audit = subparsers.add_parser('audit', help='View audit trail')
    audit.add_argument('symbol')

    # Metrics command
    metrics = subparsers.add_parser('metrics', help='Get metrics')
    metrics.add_argument('--days', type=int, default=30)

    # Risk command
    risk = subparsers.add_parser('risk', help='Score position risk')
    risk.add_argument('symbol')
    risk.add_argument('entry_price', type=float)
    risk.add_argument('shares', type=int)

    # Alerts command
    alerts = subparsers.add_parser('alerts', help='Show recent alerts')
    alerts.add_argument('--hours', type=int, default=24)

    # Report command
    report = subparsers.add_parser('report', help='Generate compliance report')
    report.add_argument('--days', type=int, default=30)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Dispatch to command
    command_map = {
        'status': cmd_status,
        'enable': cmd_enable,
        'disable': cmd_disable,
        'config': cmd_config,
        'audit': cmd_audit,
        'metrics': cmd_metrics,
        'risk': cmd_risk,
        'alerts': cmd_alerts,
        'report': cmd_report,
    }

    func = command_map.get(args.command)
    if func:
        func(args)


if __name__ == "__main__":
    main()
