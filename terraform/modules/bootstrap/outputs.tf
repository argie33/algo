output "oidc_provider_arn" {
  value = local.github_oidc_arn
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_actions.arn
}

output "github_deploy_role_name" {
  value = aws_iam_role.github_actions.name
}
