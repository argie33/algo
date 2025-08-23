#!/usr/bin/env python3
"""
Data Loader Deployment System
==============================

This script provides bulletproof deployment automation for data loaders:
1. Builds and pushes Docker images to ECR
2. Updates ECS task definitions
3. Runs ECS tasks automatically after deployment
4. Monitors execution and reports results
5. Integrates with GitHub Actions deployment pipeline

Author: Financial Platform Team
Updated: 2025-07-17
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import boto3
import yaml


class DataLoaderDeployment:
    """
    Handles deployment and execution of data loader ECS tasks
    """

    def __init__(self, region: str = None, dry_run: bool = False):
        """
        Initialize the deployment system

        Args:
            region: AWS region (defaults to environment variable)
            dry_run: If True, don't actually deploy or run tasks
        """
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.dry_run = dry_run

        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

        # Initialize AWS clients
        self.ecs_client = boto3.client("ecs", region_name=self.region)
        self.ecr_client = boto3.client("ecr", region_name=self.region)
        self.logs_client = boto3.client("logs", region_name=self.region)

        # Configuration
        self.cluster_name = "financial-platform-cluster"
        self.ecr_repository = "financial-platform-data-loaders"
        self.task_family_prefix = "financial-platform"

        self.logger.info(
            f"Data Loader Deployment initialized for region: {self.region}"
        )

    def build_and_push_docker_image(
        self, loader_name: str, dockerfile_path: str = None
    ) -> str:
        """
        Build and push Docker image for a data loader

        Args:
            loader_name: Name of the data loader
            dockerfile_path: Path to Dockerfile (optional)

        Returns:
            ECR image URI
        """
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would build and push image for {loader_name}")
            return f"123456789012.dkr.ecr.{self.region}.amazonaws.com/{self.ecr_repository}:{loader_name}-latest"

        try:
            # Get ECR login token
            token_response = self.ecr_client.get_authorization_token()
            token = token_response["authorizationData"][0]["authorizationToken"]
            registry = token_response["authorizationData"][0]["proxyEndpoint"]

            # Login to ECR
            import base64

            username, password = base64.b64decode(token).decode().split(":")

            login_cmd = [
                "docker",
                "login",
                "--username",
                username,
                "--password-stdin",
                registry,
            ]

            process = subprocess.run(
                login_cmd, input=password, text=True, capture_output=True
            )
            if process.returncode != 0:
                raise RuntimeError(f"ECR login failed: {process.stderr}")

            # Build image
            image_tag = f"{loader_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            image_uri = (
                f"{registry.replace('https://', '')}/{self.ecr_repository}:{image_tag}"
            )

            if dockerfile_path is None:
                # Use default Dockerfile
                dockerfile_path = os.path.join(
                    os.path.dirname(__file__), "Dockerfile.dataloader"
                )

            build_cmd = [
                "docker",
                "build",
                "-t",
                image_uri,
                "-f",
                dockerfile_path,
                "--build-arg",
                f"LOADER_SCRIPT={loader_name}.py",
                os.path.dirname(__file__),
            ]

            self.logger.info(f"Building Docker image: {image_uri}")
            process = subprocess.run(build_cmd, capture_output=True, text=True)
            if process.returncode != 0:
                raise RuntimeError(f"Docker build failed: {process.stderr}")

            # Push image
            push_cmd = ["docker", "push", image_uri]
            self.logger.info(f"Pushing Docker image: {image_uri}")

            process = subprocess.run(push_cmd, capture_output=True, text=True)
            if process.returncode != 0:
                raise RuntimeError(f"Docker push failed: {process.stderr}")

            self.logger.info(f"Successfully built and pushed: {image_uri}")
            return image_uri

        except Exception as e:
            self.logger.error(f"Failed to build/push image for {loader_name}: {e}")
            raise

    def create_or_update_task_definition(self, loader_name: str, image_uri: str) -> str:
        """
        Create or update ECS task definition for a data loader

        Args:
            loader_name: Name of the data loader
            image_uri: ECR image URI

        Returns:
            Task definition ARN
        """
        task_definition = {
            "family": f"{self.task_family_prefix}-{loader_name}",
            "networkMode": "awsvpc",
            "requiresCompatibilities": ["FARGATE"],
            "cpu": "512",  # 0.5 vCPU
            "memory": "1024",  # 1GB RAM
            "executionRoleArn": f"arn:aws:iam::{self._get_account_id()}:role/ecsTaskExecutionRole",
            "taskRoleArn": f"arn:aws:iam::{self._get_account_id()}:role/financial-platform-task-role",
            "containerDefinitions": [
                {
                    "name": f"{loader_name}-container",
                    "image": image_uri,
                    "essential": True,
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": f"/aws/ecs/{self.task_family_prefix}-{loader_name}",
                            "awslogs-region": self.region,
                            "awslogs-stream-prefix": "ecs",
                        },
                    },
                    "environment": [
                        {"name": "AWS_REGION", "value": self.region},
                        {"name": "LOADER_NAME", "value": loader_name},
                        {
                            "name": "DB_SECRET_ARN",
                            "value": os.getenv("DB_SECRET_ARN", ""),
                        },
                        {
                            "name": "FRED_API_KEY",
                            "value": os.getenv("FRED_API_KEY", ""),
                        },
                    ],
                    "cpu": 512,
                    "memory": 1024,
                    "memoryReservation": 512,
                }
            ],
        }

        if self.dry_run:
            self.logger.info(
                f"DRY RUN: Would create/update task definition for {loader_name}"
            )
            return f"arn:aws:ecs:{self.region}:{self._get_account_id()}:task-definition/{self.task_family_prefix}-{loader_name}:1"

        try:
            # Create CloudWatch log group if it doesn't exist
            log_group_name = f"/aws/ecs/{self.task_family_prefix}-{loader_name}"
            try:
                self.logs_client.create_log_group(logGroupName=log_group_name)
                self.logger.info(f"Created log group: {log_group_name}")
            except self.logs_client.exceptions.ResourceAlreadyExistsException:
                pass  # Log group already exists

            # Register task definition
            response = self.ecs_client.register_task_definition(**task_definition)
            task_def_arn = response["taskDefinition"]["taskDefinitionArn"]

            self.logger.info(f"Created task definition: {task_def_arn}")
            return task_def_arn

        except Exception as e:
            self.logger.error(
                f"Failed to create task definition for {loader_name}: {e}"
            )
            raise

    def run_ecs_task(
        self, loader_name: str, task_definition_arn: str, timeout_minutes: int = 30
    ) -> Dict:
        """
        Run an ECS task and monitor its execution

        Args:
            loader_name: Name of the data loader
            task_definition_arn: ARN of the task definition
            timeout_minutes: Maximum time to wait for task completion

        Returns:
            Dictionary with execution results
        """
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would run ECS task for {loader_name}")
            return {
                "success": True,
                "task_arn": f"arn:aws:ecs:{self.region}:{self._get_account_id()}:task/dummy-task-id",
                "execution_time": 60,
                "exit_code": 0,
            }

        try:
            # Run the task
            self.logger.info(f"Starting ECS task for {loader_name}")

            response = self.ecs_client.run_task(
                cluster=self.cluster_name,
                taskDefinition=task_definition_arn,
                launchType="FARGATE",
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": self._get_private_subnets(),
                        "securityGroups": [self._get_security_group()],
                        "assignPublicIp": "DISABLED",
                    }
                },
                tags=[
                    {"key": "Component", "value": "DataLoader"},
                    {"key": "LoaderName", "value": loader_name},
                    {"key": "DeployedBy", "value": "AutoDeployment"},
                    {"key": "Timestamp", "value": datetime.now().isoformat()},
                ],
            )

            if response["failures"]:
                raise RuntimeError(f"Failed to start task: {response['failures']}")

            task_arn = response["tasks"][0]["taskArn"]
            self.logger.info(f"Task started: {task_arn}")

            # Monitor task execution
            start_time = datetime.now()
            timeout_time = start_time + timedelta(minutes=timeout_minutes)

            while datetime.now() < timeout_time:
                # Check task status
                response = self.ecs_client.describe_tasks(
                    cluster=self.cluster_name, tasks=[task_arn]
                )

                if not response["tasks"]:
                    raise RuntimeError("Task disappeared during execution")

                task = response["tasks"][0]
                last_status = task["lastStatus"]

                self.logger.info(f"Task {loader_name} status: {last_status}")

                if last_status == "STOPPED":
                    # Task completed
                    execution_time = (datetime.now() - start_time).total_seconds()

                    # Get exit code
                    exit_code = None
                    for container in task.get("containers", []):
                        if container.get("exitCode") is not None:
                            exit_code = container["exitCode"]
                            break

                    # Get stop reason
                    stop_reason = task.get("stopReason", "Unknown")

                    success = exit_code == 0

                    result = {
                        "success": success,
                        "task_arn": task_arn,
                        "execution_time": execution_time,
                        "exit_code": exit_code,
                        "stop_reason": stop_reason,
                    }

                    if success:
                        self.logger.info(
                            f"Task {loader_name} completed successfully in {execution_time:.1f}s"
                        )
                    else:
                        self.logger.error(
                            f"Task {loader_name} failed with exit code {exit_code}: {stop_reason}"
                        )

                    return result

                # Wait before checking again
                time.sleep(30)

            # Task timed out
            self.logger.error(
                f"Task {loader_name} timed out after {timeout_minutes} minutes"
            )

            # Stop the task
            self.ecs_client.stop_task(
                cluster=self.cluster_name, task=task_arn, reason="Deployment timeout"
            )

            return {
                "success": False,
                "task_arn": task_arn,
                "execution_time": timeout_minutes * 60,
                "exit_code": -1,
                "stop_reason": "Timeout",
            }

        except Exception as e:
            self.logger.error(f"Failed to run ECS task for {loader_name}: {e}")
            return {"success": False, "error": str(e), "execution_time": 0}

    def get_task_logs(
        self, loader_name: str, task_arn: str, lines: int = 100
    ) -> List[str]:
        """
        Retrieve logs from a completed ECS task

        Args:
            loader_name: Name of the data loader
            task_arn: ARN of the ECS task
            lines: Number of log lines to retrieve

        Returns:
            List of log lines
        """
        try:
            log_group_name = f"/aws/ecs/{self.task_family_prefix}-{loader_name}"

            # Get log streams for this task
            response = self.logs_client.describe_log_streams(
                logGroupName=log_group_name,
                orderBy="LastEventTime",
                descending=True,
                limit=10,
            )

            if not response["logStreams"]:
                return ["No log streams found"]

            # Get logs from the most recent stream
            log_stream_name = response["logStreams"][0]["logStreamName"]

            response = self.logs_client.get_log_events(
                logGroupName=log_group_name,
                logStreamName=log_stream_name,
                limit=lines,
                startFromHead=False,
            )

            return [event["message"] for event in response["events"]]

        except Exception as e:
            self.logger.warning(f"Failed to retrieve logs for {loader_name}: {e}")
            return [f"Error retrieving logs: {e}"]

    def deploy_and_run_loader(
        self, loader_name: str, timeout_minutes: int = 30
    ) -> Dict:
        """
        Complete deployment and execution pipeline for a data loader

        Args:
            loader_name: Name of the data loader
            timeout_minutes: Maximum execution time

        Returns:
            Deployment and execution results
        """
        start_time = datetime.now()

        try:
            self.logger.info(f"=== Starting deployment for {loader_name} ===")

            # Step 1: Build and push Docker image
            image_uri = self.build_and_push_docker_image(loader_name)

            # Step 2: Create/update task definition
            task_def_arn = self.create_or_update_task_definition(loader_name, image_uri)

            # Step 3: Run the task
            execution_result = self.run_ecs_task(
                loader_name, task_def_arn, timeout_minutes
            )

            # Step 4: Get logs if task completed
            logs = []
            if "task_arn" in execution_result:
                logs = self.get_task_logs(loader_name, execution_result["task_arn"])

            end_time = datetime.now()
            total_time = (end_time - start_time).total_seconds()

            result = {
                "loader_name": loader_name,
                "success": execution_result.get("success", False),
                "total_deployment_time": total_time,
                "image_uri": image_uri,
                "task_definition_arn": task_def_arn,
                "execution_result": execution_result,
                "logs": logs[-20:] if logs else [],  # Last 20 lines
                "timestamp": start_time.isoformat(),
            }

            if result["success"]:
                self.logger.info(
                    f"Successfully deployed and ran {loader_name} in {total_time:.1f}s"
                )
            else:
                self.logger.error(f"Deployment/execution failed for {loader_name}")

            return result

        except Exception as e:
            self.logger.error(f"Deployment failed for {loader_name}: {e}")
            return {
                "loader_name": loader_name,
                "success": False,
                "error": str(e),
                "total_deployment_time": (datetime.now() - start_time).total_seconds(),
                "timestamp": start_time.isoformat(),
            }

    def deploy_multiple_loaders(
        self, loader_names: List[str], parallel: bool = False
    ) -> List[Dict]:
        """
        Deploy and run multiple data loaders

        Args:
            loader_names: List of loader names to deploy
            parallel: Whether to run deployments in parallel

        Returns:
            List of deployment results
        """
        results = []

        if parallel:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(
                        self.deploy_and_run_loader, loader_name
                    ): loader_name
                    for loader_name in loader_names
                }

                for future in as_completed(futures):
                    loader_name = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        self.logger.error(
                            f"Parallel deployment failed for {loader_name}: {e}"
                        )
                        results.append(
                            {
                                "loader_name": loader_name,
                                "success": False,
                                "error": str(e),
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
        else:
            # Sequential deployment
            for loader_name in loader_names:
                result = self.deploy_and_run_loader(loader_name)
                results.append(result)

        # Generate summary
        successful = len([r for r in results if r.get("success", False)])
        total = len(results)

        self.logger.info(f"=== Deployment Summary: {successful}/{total} successful ===")

        for result in results:
            status = "✅" if result.get("success", False) else "❌"
            self.logger.info(f"{status} {result['loader_name']}")

        return results

    def _get_account_id(self) -> str:
        """Get AWS account ID"""
        import boto3

        sts = boto3.client("sts")
        return sts.get_caller_identity()["Account"]

    def _get_private_subnets(self) -> List[str]:
        """Get private subnet IDs for ECS tasks"""
        # This would typically be retrieved from SSM Parameter Store or CloudFormation outputs
        return [
            "subnet-12345678",  # Replace with actual private subnet IDs
            "subnet-87654321",
        ]

    def _get_security_group(self) -> str:
        """Get security group ID for ECS tasks"""
        # This would typically be retrieved from SSM Parameter Store or CloudFormation outputs
        return "sg-12345678"  # Replace with actual security group ID


def main():
    """Main function for command-line usage"""
    import argparse

    parser = argparse.ArgumentParser(description="Deploy and run data loaders")
    parser.add_argument("loaders", nargs="+", help="Names of loaders to deploy")
    parser.add_argument("--region", type=str, help="AWS region")
    parser.add_argument(
        "--parallel", action="store_true", help="Run deployments in parallel"
    )
    parser.add_argument(
        "--timeout", type=int, default=30, help="Execution timeout in minutes"
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")

    args = parser.parse_args()

    # Create deployment system
    deployment = DataLoaderDeployment(region=args.region, dry_run=args.dry_run)

    # Deploy loaders
    results = deployment.deploy_multiple_loaders(args.loaders, parallel=args.parallel)

    # Exit with appropriate code
    successful = len([r for r in results if r.get("success", False)])
    if successful == len(results):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
