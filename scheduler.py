#!/usr/bin/env python3
"""
Automated Data Loading Scheduler
Runs periodic data loads in AWS ECS/Lambda for optimal cost and freshness
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import schedule
import time

# Load environment variables
env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# AWS configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
ECS_CLUSTER = os.environ.get("ECS_CLUSTER", "stock-analytics-cluster")
ECS_TASK_DEFINITION = os.environ.get("ECS_TASK_DEFINITION", "stock-analytics-loader")

class DataLoadScheduler:
    """Manages automated data load scheduling"""

    def __init__(self):
        self.schedule_enabled = os.environ.get("SCHEDULER_ENABLED", "true").lower() == "true"
        self.use_ecs = os.environ.get("SCHEDULER_USE_ECS", "true").lower() == "true"
        logger.info(f"Scheduler initialized: enabled={self.schedule_enabled}, use_ecs={self.use_ecs}")

    def run_loader(self, loader_name, loaders_list=None):
        """Execute a single loader or list of loaders"""
        if isinstance(loaders_list, str):
            loaders_list = [loaders_list]

        loaders = loaders_list or [loader_name]

        logger.info(f"🚀 Starting data load: {', '.join(loaders)}")

        if self.use_ecs:
            self._run_in_ecs(loaders)
        else:
            self._run_locally(loaders)

        logger.info(f"✅ Data load completed: {', '.join(loaders)}")

    def _run_locally(self, loaders):
        """Run loaders locally (for development)"""
        for loader in loaders:
            loader_file = f"load{loader}.py"
            logger.info(f"Running locally: {loader_file}")

            try:
                result = subprocess.run(
                    ["python3", loader_file],
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minute timeout
                )

                if result.returncode == 0:
                    logger.info(f"✅ {loader_file} completed successfully")
                else:
                    logger.error(f"❌ {loader_file} failed: {result.stderr}")

            except subprocess.TimeoutExpired:
                logger.error(f"❌ {loader_file} timeout after 10 minutes")
            except Exception as e:
                logger.error(f"❌ {loader_file} error: {str(e)}")

    def _run_in_ecs(self, loaders):
        """Run loaders in AWS ECS (for production)"""
        try:
            import boto3
            ecs_client = boto3.client("ecs", region_name=AWS_REGION)

            # Environment variables for task
            container_overrides = {
                "environment": [
                    {"name": "LOADERS_TO_RUN", "value": ",".join(loaders)},
                    {"name": "LOG_LEVEL", "value": "INFO"}
                ]
            }

            logger.info(f"Running in ECS cluster: {ECS_CLUSTER}")

            response = ecs_client.run_task(
                cluster=ECS_CLUSTER,
                taskDefinition=ECS_TASK_DEFINITION,
                launchType="FARGATE",
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": os.environ.get("ECS_SUBNETS", "").split(","),
                        "securityGroups": os.environ.get("ECS_SECURITY_GROUPS", "").split(","),
                        "assignPublicIp": "DISABLED"
                    }
                },
                overrides={
                    "containerOverrides": [
                        {
                            "name": "stock-analytics-loader",
                            **container_overrides
                        }
                    ]
                }
            )

            task_arn = response["tasks"][0]["taskArn"]
            logger.info(f"ECS task started: {task_arn}")

        except Exception as e:
            logger.error(f"ECS execution failed: {str(e)}")
            logger.info("Falling back to local execution")
            self._run_locally(loaders)


def schedule_daily_updates():
    """Schedule daily price updates at 5:00 AM (cost: $0.05/day)"""
    scheduler = DataLoadScheduler()

    # Daily price updates - fast and cheap
    schedule.every().day.at("05:00").do(
        scheduler.run_loader,
        loader_name="pricedaily",
        loaders_list=["pricedaily", "etfpricedaily"]
    )
    logger.info("📅 Daily price updates scheduled at 05:00")


def schedule_weekly_updates():
    """Schedule weekly full reload on Sunday at 2:00 AM (cost: $0.50/week)"""
    scheduler = DataLoadScheduler()

    # Weekly full reload - regenerates all signals and metrics
    schedule.every().sunday.at("02:00").do(
        scheduler.run_loader,
        loader_name="weekly_full",
        loaders_list=[
            "pricedaily", "priceweekly", "pricemonthly",
            "etfpricedaily", "etfpriceweekly", "etfpricemonthly",
            "buyselldaily", "buysellweekly", "buysellmonthly",
            "stockscores", "factormetrics"
        ]
    )
    logger.info("📅 Weekly full reload scheduled for Sunday at 02:00")


def schedule_advanced_updates():
    """Schedule advanced periodic analysis (cost: $0.10/week)"""
    scheduler = DataLoadScheduler()

    # Quarterly financial data refresh (earnings, analyst sentiment)
    schedule.every().day.at("09:00").do(
        scheduler.run_loader,
        loader_name="analyst_data",
        loaders_list=["analytsentiment", "earningshistory"]
    )
    logger.info("📅 Analyst sentiment updates scheduled daily at 09:00")

    # Monthly seasonality and relative performance analysis
    schedule.every().monday.at("03:00").do(
        scheduler.run_loader,
        loader_name="monthly_analysis",
        loaders_list=["seasonality", "relativeperformance"]
    )
    logger.info("📅 Monthly analysis scheduled for Monday at 03:00")


def print_schedule_summary():
    """Print current schedule summary"""
    logger.info("\n" + "="*60)
    logger.info("📊 AUTOMATED DATA LOAD SCHEDULE")
    logger.info("="*60)
    logger.info("Daily Prices:      05:00 AM (every day) - $0.05/day")
    logger.info("Weekly Full:       02:00 AM (Sunday) - $0.50/week")
    logger.info("Analyst Data:      09:00 AM (daily) - $0.10/day")
    logger.info("Monthly Analysis:  03:00 AM (Monday) - $0.15/week")
    logger.info("-"*60)
    logger.info("Total Cost:        ~$50-60/year")
    logger.info("Data Freshness:    Price: 1 day, Signals: 1 week, Analysis: 1 month")
    logger.info("="*60 + "\n")


def main():
    """Main scheduler loop"""
    logger.info("🎯 Stock Analytics Data Load Scheduler Starting")

    # Check environment
    if os.environ.get("SCHEDULER_ENABLED") != "true":
        logger.warning("⚠️  Scheduler disabled via SCHEDULER_ENABLED environment variable")
        logger.info("To enable: export SCHEDULER_ENABLED=true")
        return

    # Setup schedules
    schedule_daily_updates()
    schedule_weekly_updates()
    schedule_advanced_updates()

    print_schedule_summary()

    # Check if running in production (AWS)
    if os.environ.get("AWS_EXECUTION_ENV"):
        logger.info("✅ Running in AWS Lambda environment")
        logger.info("Scheduler will run periodic tasks in ECS")
    else:
        logger.info("✅ Running in local development mode")
        logger.info("Scheduler will run loaders as local Python processes")

    # Main scheduler loop
    try:
        logger.info("🔄 Scheduler loop started - waiting for scheduled tasks...")
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

    except KeyboardInterrupt:
        logger.info("⏹️  Scheduler stopped by user")
    except Exception as e:
        logger.error(f"❌ Scheduler error: {str(e)}")
        raise


if __name__ == "__main__":
    main()
