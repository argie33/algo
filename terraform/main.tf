/**
 * Stock Analytics Platform - Terraform Root Module
 *
 * Orchestrates deployment of 6 interconnected stacks:
 * 1. Bootstrap: OIDC provider for GitHub Actions
 * 2. Core: VPC, networking, ECR, S3
 * 3. Data Infrastructure: RDS, ECS cluster, Secrets Manager
 * 4. Loaders: ECS task definitions, EventBridge rules
 * 5. Webapp: Lambda API, CloudFront, Cognito
 * 6. Algo: Algorithm orchestrator Lambda
 *
 * Deployment Status: Terraform infrastructure deployment complete (2026-05-06)
 */

# ============================================================
# Module: Bootstrap (OIDC Provider)
# ============================================================
module "bootstrap" {
  source = "./modules/bootstrap"

  count = var.deploy_bootstrap ? 1 : 0

  project_name  = var.project_name
  github_org    = "argie33"
  github_repo   = "algo"
  aws_account_id = var.aws_account_id

  common_tags = local.common_tags

  depends_on = []
}

# ============================================================
# Module: Core Infrastructure (VPC, ECR, S3)
# ============================================================
module "core" {
  source = "./modules/core"

  # Only deploy core if: (1) deploy_core enabled AND (2) either creating VPC or it's not provided
  count = (var.deploy_core && var.create_vpc) ? 1 : 0

  project_name           = var.project_name
  environment            = var.environment
  aws_region             = var.aws_region
  vpc_cidr               = var.vpc_cidr
  public_subnet_cidrs    = var.public_subnet_cidrs
  private_subnet_cidrs   = var.private_subnet_cidrs
  availability_zones     = local.azs
  aws_account_id         = var.aws_account_id
  notification_email     = var.notification_email
  create_ecr_repository  = var.create_ecr_repository
  create_s3_buckets      = var.create_s3_buckets

  common_tags = local.common_tags

  # Implicit dependency through variable references
}

# ============================================================
# Module: Data Infrastructure (RDS, ECS Cluster)
# ============================================================
module "data_infrastructure" {
  source = "./modules/data_infrastructure"

  # Only deploy if: (1) deploy_data_infrastructure enabled AND (2) VPC is available (either created or provided)
  count = (var.deploy_data_infrastructure && var.create_vpc) ? 1 : 0

  project_name       = var.project_name
  environment        = var.environment
  aws_account_id     = var.aws_account_id
  notification_email = var.notification_email

  # Import from core OR use existing VPC
  vpc_id                = var.create_vpc ? module.core[0].vpc_id : var.vpc_id
  private_subnet_ids    = var.create_vpc ? module.core[0].private_subnet_ids : var.existing_private_subnet_ids
  ecs_cluster_subnet_ids = var.create_vpc ? module.core[0].private_subnet_ids : var.existing_private_subnet_ids
  rds_sg_id             = var.create_vpc ? module.core[0].rds_sg_id : null  # TODO: pass existing SG ID
  ecs_tasks_sg_id       = var.create_vpc ? module.core[0].ecs_tasks_sg_id : null  # TODO: pass existing SG ID

  # Database config
  db_name       = var.db_name
  db_user       = var.db_user
  db_password   = var.db_password
  db_instance_class = var.db_instance_class
  db_allocated_storage = var.db_allocated_storage

  # ECS config
  ecs_instance_type  = var.ecs_instance_type
  ecs_min_capacity   = var.ecs_min_capacity
  ecs_max_capacity   = var.ecs_max_capacity

  common_tags = local.common_tags

  depends_on = var.create_vpc ? [module.core[0]] : []
}

# ============================================================
# Module: Loader Tasks (ECS Task Definitions)
# ============================================================
module "loaders" {
  source = "./modules/loaders"

  count = var.deploy_loaders ? 1 : 0

  project_name        = var.project_name
  environment         = var.environment
  aws_account_id      = var.aws_account_id
  aws_region          = var.aws_region

  # Imports from core OR use existing VPC
  ecr_repository_uri = var.create_vpc ? module.core[0].ecr_repository_uri : null
  vpc_id             = var.create_vpc ? module.core[0].vpc_id : var.vpc_id
  private_subnet_ids = var.create_vpc ? module.core[0].private_subnet_ids : var.existing_private_subnet_ids

  # Imports from data infrastructure
  ecs_cluster_name    = module.data_infrastructure[0].ecs_cluster_name
  ecs_cluster_arn     = module.data_infrastructure[0].ecs_cluster_arn
  db_secret_arn       = module.data_infrastructure[0].db_secret_arn
  ecs_tasks_sg_id     = module.data_infrastructure[0].ecs_tasks_sg_id
  task_execution_role_arn = module.data_infrastructure[0].task_execution_role_arn

  common_tags = local.common_tags

  depends_on = [module.data_infrastructure[0]]
}

# ============================================================
# Module: Webapp (Lambda API, CloudFront, Cognito)
# ============================================================
module "webapp" {
  source = "./modules/webapp"

  count = var.deploy_webapp ? 1 : 0

  project_name   = var.project_name
  environment    = var.environment
  aws_account_id = var.aws_account_id
  aws_region     = var.aws_region

  # Imports from core OR use existing values
  code_bucket_name = var.create_vpc ? module.core[0].code_bucket_name : "stocks-app-code-${var.aws_account_id}"

  # Imports from data infrastructure
  db_secret_arn = module.data_infrastructure[0].db_secret_arn

  # Cognito config
  cognito_callback_urls = var.cognito_callback_urls
  cognito_logout_urls   = var.cognito_logout_urls

  common_tags = local.common_tags

  depends_on = [module.data_infrastructure[0]]
}

# ============================================================
# Module: Algo Orchestrator (Lambda Scheduler)
# ============================================================
module "algo" {
  source = "./modules/algo"

  count = var.deploy_algo ? 1 : 0

  project_name             = var.project_name
  environment              = var.environment
  aws_account_id           = var.aws_account_id
  aws_region               = var.aws_region
  lambda_memory            = var.lambda_memory
  lambda_timeout           = var.lambda_timeout

  # Imports from core OR use existing values
  algo_artifacts_bucket_name = var.create_vpc ? module.core[0].algo_artifacts_bucket_name : "stocks-algo-app-code-${var.aws_account_id}"
  code_bucket_name          = var.create_vpc ? module.core[0].code_bucket_name : "stocks-app-code-${var.aws_account_id}"

  # Imports from data infrastructure
  db_secret_arn = module.data_infrastructure[0].db_secret_arn

  common_tags = local.common_tags

  depends_on = [module.data_infrastructure[0]]
}
