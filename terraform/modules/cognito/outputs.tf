# Cognito Module - Outputs

output "user_pool_id" {
  value       = aws_cognito_user_pool.stocks_trading.id
  description = "Cognito User Pool ID"
}

output "user_pool_client_id" {
  value       = aws_cognito_user_pool_client.web_app.id
  description = "Cognito User Pool Client ID"
}

output "domain_url" {
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com"
  description = "Cognito Domain URL for OAuth"
}

output "identity_provider_url" {
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.stocks_trading.id}"
  description = "Cognito Identity Provider URL"
}
