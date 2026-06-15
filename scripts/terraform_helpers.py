"""Helper functions to dynamically discover infrastructure names from Terraform outputs."""

import json
import subprocess
import os
from typing import Optional


def get_terraform_output(output_name: str) -> Optional[str]:
    """Fetch a Terraform output value."""
    try:
        result = subprocess.run(
            ["terraform", "output", "-raw", output_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.strip()
    except Exception as e:
        print(f"Warning: Could not get Terraform output '{output_name}': {e}")
    return None


def get_infrastructure_names(environment: str = "dev") -> dict:
    """Get all infrastructure resource names, preferring Terraform outputs when available."""

    project_name = "algo"

    # Base names (following Terraform naming conventions)
    names = {
        "project_name": project_name,
        "environment": environment,
        "region": "us-east-1",
        "cognito_pool_name": f"{project_name}-pool-{environment}",
        "cognito_client_name": f"{project_name}-web-app-{environment}",
        "ecs_cluster_name": f"{project_name}-cluster",
        "rds_instance_id": f"{project_name}-db",
        "sns_topic_name": f"{project_name}-loader-failures-{environment}",
        "dynamodb_table_name": f"{project_name}-orchestrator-halt-{environment}",
    }

    # Try to fetch actual Terraform outputs (prefer these over defaults)
    if os.path.exists("terraform"):
        os.chdir("terraform")

        tf_pool_id = get_terraform_output("cognito_user_pool_id")
        if tf_pool_id:
            names["cognito_user_pool_id"] = tf_pool_id

        tf_cluster = get_terraform_output("ecs_cluster_name")
        if tf_cluster:
            names["ecs_cluster_name"] = tf_cluster

        tf_region = get_terraform_output("aws_region")
        if tf_region:
            names["region"] = tf_region

        os.chdir("..")

    return names


def get_loader_log_groups(names: dict) -> dict:
    """Get CloudWatch log group names for loaders."""
    base = names["cognito_pool_name"].split("-")[0]  # "algo"
    names["environment"]

    return {
        "stock_prices_daily": f"/ecs/{base}-stock_prices_daily-loader",
        "technical_data_daily": f"/ecs/{base}-technical_data_daily-loader",
        "buy_sell_daily": f"/ecs/{base}-buy_sell_daily-loader",
        "signal_quality_scores": f"/ecs/{base}-signal_quality_scores-loader",
        "algo_metrics_daily": f"/ecs/{base}-algo_metrics_daily-loader",
        "swing_trader_scores": f"/ecs/{base}-swing_trader_scores-loader",
        "company_profile": f"/ecs/{base}-company_profile-loader",
        "stability_metrics": f"/ecs/{base}-stability_metrics-loader",
        "analyst_sentiment": f"/ecs/{base}-analyst_sentiment-loader",
        "analyst_upgrades_downgrades": f"/ecs/{base}-analyst_upgrades_downgrades-loader",
        "market_health_daily": f"/ecs/{base}-market_health_daily-loader",
        "trend_template_data": f"/ecs/{base}-trend_template_data-loader",
        "fred_economic_data": f"/ecs/{base}-fred_economic_data-loader",
        "growth_metrics": f"/ecs/{base}-growth_metrics-loader",
        "quality_metrics": f"/ecs/{base}-quality_metrics-loader",
        "value_metrics": f"/ecs/{base}-value_metrics-loader",
    }


if __name__ == "__main__":
    names = get_infrastructure_names()
    print(json.dumps(names, indent=2))

    print("\nLoader log groups:")
    log_groups = get_loader_log_groups(names)
    print(json.dumps(log_groups, indent=2))
