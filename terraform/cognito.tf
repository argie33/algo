# Cognito Authentication Module
# Provides AWS Cognito user pool, client, and domain for web authentication

module "cognito" {
  source = "./modules/cognito"

  project_name                 = var.project_name
  environment                  = var.environment
  aws_region                   = var.aws_region
  domain_name                  = try(var.domain_name, "example.com")
  cloudfront_domain            = module.services.cloudfront_domain_name != null ? module.services.cloudfront_domain_name : var.cloudfront_domain
  common_tags                  = local.common_tags
  cognito_test_user_email      = var.cognito_test_user_email
  cognito_custom_email_enabled = var.cognito_custom_email_enabled
  cognito_sender_email         = var.cognito_sender_email
  mfa_configuration            = var.cognito_mfa_configuration
  advanced_security_mode       = var.cognito_advanced_security_mode

  depends_on = [module.services]
}

# All Cognito outputs are defined in outputs.tf to avoid duplication at root level
