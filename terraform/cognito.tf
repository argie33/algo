# Cognito Authentication Module
# Provides AWS Cognito user pool, client, and domain for web authentication

module "cognito" {
  source = "./modules/cognito"

  project_name                = var.project_name
  environment                 = var.environment
  aws_region                  = var.aws_region
  domain_name                 = try(var.domain_name, "example.com")
  cloudfront_domain           = var.cloudfront_domain
  common_tags                 = local.common_tags
  cognito_test_user_email     = var.cognito_test_user_email
}

# Output credentials for frontend configuration
output "cognito_user_pool_id" {
  value       = module.cognito.user_pool_id
  description = "Cognito User Pool ID for frontend"
}

output "cognito_user_pool_client_id" {
  value       = module.cognito.user_pool_client_id
  description = "Cognito User Pool Client ID for frontend"
}

output "cognito_domain_url" {
  value       = module.cognito.domain_url
  description = "Cognito OAuth domain URL"
}

output "cognito_identity_provider_url" {
  value       = module.cognito.identity_provider_url
  description = "Cognito Identity Provider URL"
}
