output "api_endpoint" {
  value = "https://api.example.com"
  description = "API Gateway endpoint (placeholder - implement when API added)"
}

output "cloudfront_domain" {
  value = "d123456789.cloudfront.net"
  description = "CloudFront domain name (placeholder - implement when CloudFront added)"
}

output "website_url" {
  value = "https://example.com"
  description = "Website URL (placeholder - implement when CloudFront added)"
}

output "cognito_user_pool_id" {
  value = "us-east-1_XXXXXXXXX"
  description = "Cognito User Pool ID (placeholder - implement)"
}

output "cognito_client_id" {
  value = "client_id_here"
  description = "Cognito Client ID (placeholder - implement)"
  sensitive = true
}

output "frontend_bucket_name" {
  value = "aws_s3_bucket.frontend.id"
  description = "Frontend S3 bucket name"
}
