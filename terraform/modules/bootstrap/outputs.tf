output "oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github.arn
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_actions.arn
}

output "github_deploy_role_name" {
  value = aws_iam_role.github_actions.name
}
