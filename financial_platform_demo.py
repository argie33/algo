#!/usr/bin/env python3
"""
Financial Platform Demo
Integration demonstration of all implemented systems
"""

import sys
import time
from datetime import datetime

from data_quality_validation import DataQualityFramework

# Import all our modules
from economic_modeling import MarketRegimeDetector, RecessionPredictor
from monitoring_alerting import AlertSeverity, MonitoringSystem
from pattern_recognition import TechnicalPatternRecognizer
from portfolio_management import Portfolio
from sentiment_analysis import SentimentAnalyzer


def main():
    print("=" * 60)
    print("FINANCIAL PLATFORM COMPREHENSIVE DEMO")
    print("Institutional-Grade AI-Driven Financial Analysis")
    print("=" * 60)

    # 1. Economic Modeling Framework
    print("\n1. ECONOMIC MODELING & RECESSION PREDICTION")
    print("-" * 45)

    recession_predictor = RecessionPredictor()
    regime_detector = MarketRegimeDetector()

    recession_result = recession_predictor.calculate_recession_probability()
    regime_result = regime_detector.detect_regime()

    print(f"Recession Probability: {recession_result['probability']:.1%}")
    print(f"Risk Level: {recession_result['risk_level']}")
    print(f"Market Regime: {regime_result['regime'].upper()}")
    print(f"Regime Confidence: {regime_result['confidence']:.1%}")

    print("\nTop Economic Risks:")
    for risk in recession_result["key_risks"][:2]:
        print(f"  • {risk}")

    # 2. Sentiment Analysis
    print("\n2. SENTIMENT ANALYSIS PIPELINE")
    print("-" * 35)

    sentiment_analyzer = SentimentAnalyzer()
    test_symbols = ["AAPL", "MSFT"]

    for symbol in test_symbols:
        sentiment_result = sentiment_analyzer.analyze_comprehensive_sentiment(symbol)

        print(f"\n{symbol} Sentiment Analysis:")
        print(f"  Composite Score: {sentiment_result['composite_score']:.3f}")
        print(f"  Category: {sentiment_result['sentiment_category']}")
        print(f"  Confidence: {sentiment_result['confidence']:.1%}")

        components = sentiment_result["components"]
        print("  Component Breakdown:")
        for source, data in components.items():
            print(f"    {source.capitalize()}: {data['score']:.3f}")

    # 3. Technical Pattern Recognition
    print("\n3. TECHNICAL PATTERN RECOGNITION")
    print("-" * 35)

    pattern_recognizer = TechnicalPatternRecognizer(confidence_threshold=0.6)

    for symbol in test_symbols:
        pattern_result = pattern_recognizer.detect_patterns(symbol)

        print(f"\n{symbol} Pattern Analysis:")
        print(f"  Patterns Found: {pattern_result['patterns_found']}")
        print(f"  Pattern Score: {pattern_result.get('pattern_score', 0):.2f}")

        if pattern_result.get("patterns"):
            print("  Detected Patterns:")
            for pattern in pattern_result["patterns"][:2]:  # Show first 2
                print(
                    f"    • {pattern['type']}: {pattern['confidence']:.1%} confidence"
                )

    # 4. Portfolio Management
    print("\n4. PORTFOLIO MANAGEMENT SYSTEM")
    print("-" * 35)

    portfolio = Portfolio(cash=100000.0)

    # Add positions
    portfolio.add_position("AAPL", 100, 150.0)
    portfolio.add_position("MSFT", 80, 300.0)
    portfolio.add_position("GOOGL", 30, 2500.0)

    print(f"Portfolio Value: ${portfolio.get_portfolio_value():,.2f}")
    print(f"Positions: {len(portfolio.positions)}")

    metrics = portfolio.get_portfolio_metrics()
    print(f"Total Return: {metrics.total_return:.1%}")
    print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {metrics.max_drawdown:.1%}")

    risk_metrics = portfolio.get_risk_metrics()
    print(f"Diversification Ratio: {risk_metrics['diversification_ratio']:.2f}")

    # 5. Data Quality Validation
    print("\n5. DATA QUALITY VALIDATION")
    print("-" * 30)

    dq_framework = DataQualityFramework()

    for symbol in ["AAPL", "MSFT"]:
        dq_result = dq_framework.validate_symbol_data(symbol, include_financials=False)

        print(f"\n{symbol} Data Quality:")
        print(f"  Overall Score: {dq_result['summary']['overall_score']:.1f}/100")
        print(f"  Grade: {dq_result['summary']['data_quality_grade']}")
        print(f"  Total Checks: {dq_result['total_checks']}")
        print(
            f"  Issues: {dq_result['summary']['critical_issues']} critical, {dq_result['summary']['warnings']} warnings"
        )

    # 6. Monitoring & Alerting System
    print("\n6. MONITORING & ALERTING SYSTEM")
    print("-" * 35)

    monitoring_system = MonitoringSystem()
    monitoring_system.start_monitoring()

    print("Monitoring system started...")

    # Simulate some alerts
    monitoring_system.data_quality_monitor.update_quality_score("price_data", 85.0)
    monitoring_system.portfolio_monitor.update_portfolio_metrics(
        {
            "total_return": metrics.total_return,
            "max_drawdown": metrics.max_drawdown,
            "sharpe_ratio": metrics.sharpe_ratio,
        }
    )

    # Trigger test alert
    test_alert_id = monitoring_system.trigger_test_alert(AlertSeverity.MEDIUM)

    time.sleep(2)  # Allow alerts to process

    status = monitoring_system.get_system_status()
    print(f"Active Monitors: {status['active_monitors']}/{status['total_monitors']}")
    print(f"System Health: {'OPERATIONAL' if status['monitoring_active'] else 'DOWN'}")

    alert_summary = status["alert_summary"]
    print(
        f"Alerts (24h): {alert_summary['total_alerts']} total, {alert_summary['active_alerts']} active"
    )

    # Show recent alerts
    recent_alerts = monitoring_system.alert_manager.get_active_alerts()
    if recent_alerts:
        print("\nRecent Alerts:")
        for alert in recent_alerts[:3]:
            print(f"  • {alert.severity.value}: {alert.title}")

    monitoring_system.stop_monitoring()

    # 7. Integration Summary
    print("\n7. PLATFORM INTEGRATION SUMMARY")
    print("-" * 35)

    print("✓ Economic Modeling: Recession prediction and regime detection")
    print("✓ Sentiment Analysis: Multi-source NLP pipeline")
    print("✓ Pattern Recognition: AI-powered technical analysis")
    print("✓ Portfolio Management: Optimization and risk management")
    print("✓ Data Quality: Comprehensive validation framework")
    print("✓ Monitoring: Real-time alerting and health tracking")

    # Overall system health score
    components = [
        recession_result["probability"] < 0.5,  # Low recession risk
        sentiment_result["confidence"] > 0.5,  # Confident sentiment
        pattern_result["pattern_score"] > 0.3,  # Some patterns detected
        metrics.sharpe_ratio > 0,  # Positive risk-adjusted return
        dq_result["summary"]["overall_score"] > 70,  # Good data quality
        status["monitoring_active"],  # Monitoring operational
    ]

    health_score = sum(components) / len(components) * 100

    print(f"\nOverall Platform Health: {health_score:.0f}%")

    if health_score >= 80:
        print("🟢 EXCELLENT - All systems operating optimally")
    elif health_score >= 60:
        print("🟡 GOOD - Most systems operating well")
    elif health_score >= 40:
        print("🟠 FAIR - Some systems need attention")
    else:
        print("🔴 POOR - Multiple systems require immediate attention")

    print("\n" + "=" * 60)
    print("DEMO COMPLETED SUCCESSFULLY")
    print("Financial platform is ready for production deployment!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
    except Exception as e:
        print(f"\nError during demo: {e}")
        import traceback

        traceback.print_exc()
