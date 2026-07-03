#!/usr/bin/env python3
"""Phase 4 CloudWatch Monitoring Setup - Python Implementation"""

import argparse
import json
import logging
import sys

import boto3

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class Phase4Monitor:
    """Manages Phase 4 CloudWatch monitoring setup"""

    def __init__(self, environment: str, dry_run: bool = False):
        self.environment = environment
        self.dry_run = dry_run
        self.aws_region = "us-east-1"

        self.logs_client = boto3.client("logs", region_name=self.aws_region)
        self.cloudwatch_client = boto3.client(
            "cloudwatch", region_name=self.aws_region
        )
        self.sns_client = boto3.client("sns", region_name=self.aws_region)
        self.sts_client = boto3.client("sts", region_name=self.aws_region)

        self.account_id = self.sts_client.get_caller_identity()["Account"]

        self.log_group_api = f"/aws/lambda/algo-api-{environment}"
        self.log_group_algo = f"/aws/lambda/algo-algo-{environment}"
        self.log_group_circuit_breaker = (
            f"/aws/lambda/algo-circuit-breaker-{environment}"
        )

        self.alerts_topic_arn = (
            f"arn:aws:sns:{self.aws_region}:{self.account_id}:algo-alerts-{environment}"
        )
        self.critical_topic_arn = (
            f"arn:aws:sns:{self.aws_region}:{self.account_id}:algo-critical-{environment}"
        )

    def _execute(self, description: str, operation):
        """Execute operation respecting dry-run mode"""
        if self.dry_run:
            logger.info(f"[DRY-RUN] {description}")
        else:
            logger.info(description)
            try:
                return operation()
            except Exception as e:
                logger.error(f"Error: {e}")
                raise

    def create_sns_topics(self):
        """Create SNS topics"""
        logger.info("\n====== Phase 1: Create SNS Topics ======\n")

        def create():
            self.sns_client.create_topic(name=f"algo-alerts-{self.environment}")
            self.sns_client.create_topic(name=f"algo-critical-{self.environment}")

        self._execute("Create SNS topics", create)

    def create_metric_filters(self):
        """Create metric filters"""
        logger.info("\n====== Phase 2: Create Metric Filters ======\n")

        filters = [
            (self.log_group_api, "DataUnavailableErrors", '[... "data_unavailable" = true, ...]'),
            (self.log_group_algo, "DataUnavailableErrors", '[... "data_unavailable" = true, ...]'),
            (self.log_group_api, "ValidationErrors", '[... "[HARDENING]" ... ("validation error" || "StrictValidationError"), ...]'),
            (self.log_group_circuit_breaker, "CircuitBreakerHalts", '[... "[CIRCUIT_BREAKER]" ... "HALTING TRADING", ...]'),
            (self.log_group_algo, "CircuitBreakerHalts", '[... "[CIRCUIT_BREAKER]" ... "HALTING TRADING", ...]'),
            (self.log_group_api, "DataStalenessErrors", '[... "[DATA QUALITY]" ... ("stale" = true || "stale_data"), ...]'),
            (self.log_group_api, "HardeningErrors", '[... "[HARDENING]" ... ("error" || "ERROR"), ...]'),
            (self.log_group_api, "AllErrors", '[... ("ERROR" || "Exception" || "error:" || "failed"), ...]'),
        ]

        for log_group, filter_name, pattern in filters:
            def create():
                self.logs_client.put_metric_filter(
                    logGroupName=log_group,
                    filterName=filter_name,
                    filterPattern=pattern,
                    metricTransformations=[
                        {
                            "metricName": filter_name,
                            "metricNamespace": "Algo/FailFast",
                            "metricValue": "1",
                            "defaultValue": 0,
                        }
                    ],
                )

            self._execute(f"Create metric filter {filter_name}", create)

    def create_alarms(self):
        """Create CloudWatch alarms"""
        logger.info("\n====== Phase 3: Create CloudWatch Alarms ======\n")

        alarms = [
            ("algo-data-unavailability-alert", "DataUnavailableErrors", 5, self.alerts_topic_arn),
            ("algo-validation-error-alert", "ValidationErrors", 10, self.alerts_topic_arn),
            ("algo-circuit-breaker-halt", "CircuitBreakerHalts", 1, self.critical_topic_arn),
            ("algo-data-staleness-alert", "DataStalenessErrors", 3, self.alerts_topic_arn),
            ("algo-hardening-error-alert", "HardeningErrors", 15, self.alerts_topic_arn),
        ]

        for base_name, metric_name, threshold, topic_arn in alarms:
            alarm_name = f"{base_name}-{self.environment}"

            def create():
                self.cloudwatch_client.put_metric_alarm(
                    AlarmName=alarm_name,
                    MetricName=metric_name,
                    Namespace="Algo/FailFast",
                    Statistic="Sum",
                    Period=300 if metric_name != "CircuitBreakerHalts" else 60,
                    Threshold=threshold,
                    ComparisonOperator="GreaterThanOrEqualToThreshold",
                    EvaluationPeriods=1,
                    TreatMissingData="notBreaching",
                    AlarmActions=[topic_arn],
                )

            self._execute(f"Create alarm {alarm_name}", create)

    def create_log_retention(self):
        """Set log retention policies"""
        logger.info("\n====== Phase 4: Set Log Retention ======\n")

        log_groups = [self.log_group_api, self.log_group_algo, self.log_group_circuit_breaker]

        for log_group in log_groups:
            def create():
                self.logs_client.put_retention_policy(
                    logGroupName=log_group,
                    retentionInDays=30,
                )

            self._execute(f"Set retention for {log_group}", create)

    def run(self):
        """Execute full setup"""
        logger.info("=" * 60)
        logger.info("Phase 4: CloudWatch Monitoring Setup")
        logger.info("=" * 60)
        logger.info(f"Environment: {self.environment}")
        logger.info(f"Dry Run: {self.dry_run}")
        logger.info("=" * 60)

        try:
            self.create_sns_topics()
            self.create_metric_filters()
            self.create_alarms()
            self.create_log_retention()

            logger.info("\n" + "=" * 60)
            logger.info("Phase 4 Setup Complete")
            logger.info("=" * 60)
            logger.info(f"\nSNS Topics:")
            logger.info(f"  Alerts: {self.alerts_topic_arn}")
            logger.info(f"  Critical: {self.critical_topic_arn}")
            logger.info("\nNext Steps:")
            logger.info("  1. Configure SNS subscriptions")
            logger.info("  2. Deploy dashboard: aws cloudwatch put-dashboard --dashboard-name algo-failfast-" + self.environment + " --dashboard-body file://monitoring/PHASE4_CLOUDWATCH_DASHBOARD.json")
            logger.info("  3. Run tests: bash monitoring/PHASE4_TESTING_STEPS.md")

            if self.dry_run:
                logger.info("\n[DRY-RUN MODE] No changes were made.")

        except Exception as e:
            logger.error(f"Setup failed: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Phase 4 CloudWatch Monitoring Setup")
    parser.add_argument("--environment", choices=["dev", "staging", "prod"], default="dev")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    monitor = Phase4Monitor(environment=args.environment, dry_run=args.dry_run)
    monitor.run()


if __name__ == "__main__":
    main()
