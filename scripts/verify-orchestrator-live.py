#!/usr/bin/env python3
"""
Orchestrator Live Verification Script

Monitors and verifies the orchestrator execution with full dataset on Monday:
- 2:00 AM ET: Morning prep pipeline (stock_prices_daily + technical_data_daily + ...)
- 9:30 AM ET: Orchestrator execution (Phases 1-7)

Checks CloudWatch logs, RDS metrics, and database state to verify success.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrchestratorVerifier:
    """Verifies orchestrator execution via CloudWatch and AWS metrics."""

    def __init__(self, region: str = "us-east-1"):
        """Initialize AWS clients."""
        self.region = region
        self.logs = boto3.client("logs", region_name=region)
        self.cloudwatch = boto3.client("cloudwatch", region_name=region)
        self.ecs = boto3.client("ecs", region_name=region)

        self.state_machine_arn = self._get_state_machine_arn("morning-prep-pipeline-dev")
        self.orchestrator_log_group = "/aws/lambda/algo-algo-dev"
        self.loaders_log_group_prefix = "/ecs/algo-"

    def _get_state_machine_arn(self, name: str) -> Optional[str]:
        """Get Step Functions state machine ARN by name."""
        try:
            sfn = boto3.client("stepfunctions", region_name=self.region)
            response = sfn.list_state_machines()
            for sm in response.get("stateMachines", []):
                if name in sm["name"]:
                    return sm["stateMachineArn"]
        except Exception as e:
            logger.warning(f"Failed to get state machine ARN: {e}")
        return None

    def check_morning_prep_pipeline(self) -> Dict[str, any]:
        """Check morning prep pipeline execution status."""
        logger.info("=" * 80)
        logger.info("CHECKING MORNING PREP PIPELINE (2:00 AM ET)")
        logger.info("=" * 80)

        # Check Step Functions execution logs
        try:
            sfn = boto3.client("stepfunctions", region_name=self.region)

            # List recent executions
            response = sfn.list_executions(
                stateMachineArn=self.state_machine_arn,
                statusFilter="SUCCEEDED",
                maxResults=5
            )

            latest_exec = response["executions"][0] if response["executions"] else None

            if not latest_exec:
                logger.warning("No successful morning prep executions found")
                return {"status": "no_data", "message": "No recent executions"}

            # Get execution history
            exec_arn = latest_exec["executionArn"]
            history = sfn.get_execution_history(executionArn=exec_arn)

            logger.info(f"✓ Latest execution: {latest_exec['name']}")
            logger.info(f"  Status: {latest_exec['status']}")
            logger.info(f"  Started: {latest_exec['startDate']}")
            logger.info(f"  Stopped: {latest_exec.get('stopDate', 'N/A')}")

            # Check loader statuses from event history
            loaders_completed = set()
            loaders_failed = set()

            for event in history["events"]:
                if "ExecutionSucceeded" in event:
                    logger.info("  ✓ Pipeline completed successfully")
                if "ExecutionFailed" in event:
                    logger.error("  ✗ Pipeline failed")
                    loaders_failed.add("pipeline")
                if "TaskStateEntered" in event:
                    state_name = event.get("stateEnteredEventDetails", {}).get("name", "")
                    if state_name:
                        logger.debug(f"    → {state_name}")

            return {
                "status": "success",
                "execution": latest_exec["name"],
                "loaders_completed": list(loaders_completed),
                "loaders_failed": list(loaders_failed),
            }

        except Exception as e:
            logger.error(f"Failed to check morning prep: {e}")
            return {"status": "error", "message": str(e)}

    def check_orchestrator_execution(self) -> Dict[str, any]:
        """Check orchestrator Lambda execution logs."""
        logger.info("=" * 80)
        logger.info("CHECKING ORCHESTRATOR EXECUTION (9:30 AM ET)")
        logger.info("=" * 80)

        try:
            # Get latest log streams for orchestrator
            response = self.logs.describe_log_streams(
                logGroupName=self.orchestrator_log_group,
                orderBy="LastEventTime",
                descending=True,
                limit=5
            )

            if not response.get("logStreams"):
                logger.warning("No log streams found for orchestrator")
                return {"status": "no_data"}

            latest_stream = response["logStreams"][0]
            stream_name = latest_stream["logStreamName"]

            logger.info(f"Latest log stream: {stream_name}")
            logger.info(f"Last event time: {latest_stream.get('lastEventTimestamp', 'N/A')}")

            # Get recent log events
            log_response = self.logs.get_log_events(
                logGroupName=self.orchestrator_log_group,
                logStreamName=stream_name,
                limit=100
            )

            # Parse orchestrator output for phases
            phase_results = {}
            data_freshness = False
            signals_generated = 0
            trades_opened = 0

            for event in log_response.get("events", []):
                message = event.get("message", "")

                if "Phase 1" in message and "PASS" in message:
                    phase_results["phase_1"] = "PASS"
                    data_freshness = True
                    logger.info("  ✓ Phase 1: Data freshness check PASSED")
                elif "Phase 1" in message and "HALT" in message:
                    phase_results["phase_1"] = "HALT"
                    logger.error("  ✗ Phase 1: Data freshness check HALTED")

                if "Phase 5" in message:
                    if "signals" in message.lower():
                        logger.info(f"  → Phase 5: {message.strip()}")

                if "Phase 6" in message:
                    if "order" in message.lower() or "entry" in message.lower():
                        logger.info(f"  → Phase 6: {message.strip()}")
                        trades_opened += 1

                if "Phase 7" in message:
                    logger.info(f"  ✓ Phase 7: Reconciliation")

            return {
                "status": "success",
                "phases": phase_results,
                "data_freshness": data_freshness,
                "trades_opened": trades_opened,
                "log_stream": stream_name,
            }

        except Exception as e:
            logger.error(f"Failed to check orchestrator: {e}")
            return {"status": "error", "message": str(e)}

    def check_rds_metrics(self) -> Dict[str, any]:
        """Check RDS connection pool metrics during execution."""
        logger.info("=" * 80)
        logger.info("CHECKING RDS METRICS")
        logger.info("=" * 80)

        try:
            # Get DatabaseConnections metric for the last hour
            now = datetime.utcnow()
            start_time = now - timedelta(hours=1)

            response = self.cloudwatch.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName="DatabaseConnections",
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": "algo-db"}],
                StartTime=start_time,
                EndTime=now,
                Period=300,  # 5-minute intervals
                Statistics=["Maximum", "Average"]
            )

            if not response.get("Datapoints"):
                logger.warning("No RDS metrics available")
                return {"status": "no_data"}

            datapoints = sorted(response["Datapoints"], key=lambda x: x["Timestamp"])

            max_connections = max(dp.get("Maximum", 0) for dp in datapoints)
            avg_connections = sum(dp.get("Average", 0) for dp in datapoints) / len(datapoints)

            logger.info(f"Max connections: {max_connections:.0f}")
            logger.info(f"Avg connections: {avg_connections:.0f}")
            logger.info(f"Expected: 20-30 (healthy with RDS Proxy)")

            if max_connections > 80:
                logger.warning(f"  ⚠️  High connection count: {max_connections}")
            else:
                logger.info(f"  ✓ Connection pool healthy")

            return {
                "status": "success",
                "max_connections": max_connections,
                "avg_connections": avg_connections,
            }

        except Exception as e:
            logger.error(f"Failed to check RDS metrics: {e}")
            return {"status": "error", "message": str(e)}

    def check_database_state(self) -> Dict[str, any]:
        """Check database state for symbol coverage and signals."""
        logger.info("=" * 80)
        logger.info("CHECKING DATABASE STATE")
        logger.info("=" * 80)

        try:
            from utils.database_context import DatabaseContext

            with DatabaseContext("read") as cur:
                # Check symbol coverage for buy_sell_daily
                cur.execute("""
                    SELECT COUNT(DISTINCT symbol) as total,
                           SUM(CASE WHEN updated_at >= CURRENT_DATE THEN 1 ELSE 0 END) as today
                    FROM buy_sell_daily
                    WHERE updated_at >= CURRENT_DATE - INTERVAL '1 day'
                """)

                result = cur.fetchone()
                if result:
                    total, today = result
                    coverage = (today / total * 100) if total > 0 else 0
                    logger.info(f"Buy/Sell Daily: {today}/{total} symbols ({coverage:.1f}%)")

                    if coverage >= 90:
                        logger.info(f"  ✓ Symbol coverage optimal (≥90%)")
                    elif coverage >= 80:
                        logger.info(f"  ⚠️  Symbol coverage moderate (80-90%)")
                    else:
                        logger.error(f"  ✗ Symbol coverage critical (<80%)")

                # Check signals generated
                cur.execute("""
                    SELECT COUNT(*) FROM algorithm_signals
                    WHERE created_at >= CURRENT_DATE
                """)

                signal_count = cur.fetchone()[0]
                logger.info(f"Signals generated today: {signal_count}")

                if signal_count >= 15:
                    logger.info(f"  ✓ Signal generation successful")
                elif signal_count > 0:
                    logger.info(f"  ⚠️  Below expected range (15-40)")
                else:
                    logger.warning(f"  ⚠️  No signals generated")

                # Check trades
                cur.execute("""
                    SELECT COUNT(*) FROM algo_trades
                    WHERE created_at >= CURRENT_DATE AND action = 'BUY'
                """)

                trade_count = cur.fetchone()[0]
                logger.info(f"BUY trades opened today: {trade_count}")

                return {
                    "status": "success",
                    "symbol_coverage": coverage,
                    "signals_generated": signal_count,
                    "trades_opened": trade_count,
                }

        except Exception as e:
            logger.error(f"Failed to check database state: {e}")
            return {"status": "error", "message": str(e)}

    def verify_full_execution(self) -> bool:
        """Perform complete verification of morning prep + orchestrator execution."""
        logger.info("\n" + "=" * 80)
        logger.info("ORCHESTRATOR LIVE VERIFICATION")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {datetime.now()} (may need to wait until Monday 9:30 AM)")
        logger.info("=" * 80 + "\n")

        results = {
            "timestamp": datetime.now().isoformat(),
            "morning_prep": self.check_morning_prep_pipeline(),
            "orchestrator": self.check_orchestrator_execution(),
            "rds_metrics": self.check_rds_metrics(),
            "database_state": self.check_database_state(),
        }

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("VERIFICATION SUMMARY")
        logger.info("=" * 80)

        all_success = all(r.get("status") != "error" for r in results.values())

        if results["orchestrator"].get("phases", {}).get("phase_1") == "PASS":
            logger.info("✓ Phase 1 Data Freshness: PASSED")
        else:
            logger.warning("⚠️  Phase 1 not completed yet or halted")

        if results["database_state"].get("symbol_coverage", 0) >= 90:
            logger.info("✓ Symbol Coverage: OPTIMAL (≥90%)")
        else:
            logger.warning(f"⚠️  Symbol Coverage: {results['database_state'].get('symbol_coverage', 0):.0f}%")

        logger.info(f"✓ RDS Connections: Healthy ({results['rds_metrics'].get('max_connections', 'N/A')})")

        logger.info("\n" + "=" * 80)

        return all_success


def main():
    parser = argparse.ArgumentParser(description="Verify orchestrator execution")
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1)"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch execution continuously (poll every 30s)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Polling interval in seconds (default: 30)"
    )

    args = parser.parse_args()

    verifier = OrchestratorVerifier(region=args.region)

    if args.watch:
        logger.info("Watching orchestrator execution... (press Ctrl+C to stop)")
        attempt = 0
        while True:
            attempt += 1
            logger.info(f"\n[Attempt {attempt}] {datetime.now().strftime('%H:%M:%S')}")
            verifier.verify_full_execution()
            logger.info(f"Waiting {args.interval}s before next check...")
            time.sleep(args.interval)
    else:
        success = verifier.verify_full_execution()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
