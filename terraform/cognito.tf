# Cognito Authentication Module
# Provides AWS Cognito user pool, client, and domain for web authentication

module "cognito" {
  source = "./modules/cognito"

  environment = var.environment
  aws_region  = var.aws_region
  domain_name = var.domain_name

  tags = merge(
    var.common_tags,
    {
      Module = "cognito"
    }
  )
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
