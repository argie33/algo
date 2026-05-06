locals {
  # Naming conventions
  project = var.project_name
  env     = var.environment

  # Stack names (match CloudFormation convention: stocks-{component}[-{env}])
  stack_names = {
    bootstrap = "${local.project}-oidc"
    core      = "${local.project}-core"
    data      = "${local.project}-data"
    loaders   = "${local.project}-loaders"
    webapp    = "${local.project}-webapp-${local.env}"
    algo      = "${local.project}-algo-${local.env}"
  }

  # Common tags applied to all resources
  common_tags = merge(
    {
      Project    = "stocks-analytics"
      Environment = local.env
      ManagedBy  = "terraform"
      CreatedAt  = timestamp()
    },
    var.additional_tags
  )

  # Availability zones
  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  # S3 bucket naming (must be globally unique)
  bucket_suffix = var.aws_account_id

  # Export/Import prefixes (match CloudFormation exports)
  exports = {
    # Bootstrap
    oidc_provider_arn     = "StocksOidc-WebIdentityProviderArn"
    github_deploy_role    = "StocksOidc-GitHubActionsDeployRoleArn"

    # Core
    vpc_id                = "StocksCore-VpcId"
    public_subnet_1       = "StocksCore-PublicSubnet1Id"
    public_subnet_2       = "StocksCore-PublicSubnet2Id"
    private_subnet_1      = "StocksCore-PrivateSubnet1Id"
    private_subnet_2      = "StocksCore-PrivateSubnet2Id"
    ecr_uri               = "StocksCore-ContainerRepositoryUri"
    cf_templates_bucket   = "StocksCore-CfTemplatesBucketName"
    code_bucket           = "StocksCore-CodeBucketName"
    algo_artifacts_bucket = "StocksCore-AlgoArtifactsBucketName"
    bastion_sg            = "StocksCore-BastionSecurityGroupId"
    vpce_sg               = "StocksCore-VpcEndpointSecurityGroupId"

    # Data Infrastructure
    db_endpoint            = "StocksApp-DBEndpoint"
    db_port                = "StocksApp-DBPort"
    db_name                = "StocksApp-DBName"
    db_secret_arn          = "StocksApp-SecretArn"
    algo_secret_arn        = "StocksApp-AlgoSecretsSecretArn"
    ecs_cluster_arn        = "StocksApp-ClusterArn"
    ecs_task_execution_role = "StocksApp-EcsTaskExecutionRoleArn"
    ecs_tasks_sg           = "StocksApp-EcsTasksSecurityGroupId"

    # Loaders
    loaders_state_machine  = "StocksLoaders-StateMachineArn"
  }
}

# Get available AZs for the region
data "aws_availability_zones" "available" {
  state = "available"
}
