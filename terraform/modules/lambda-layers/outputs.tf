output "shared_deps_layer_arn" {
  description = "ARN of the shared dependencies Lambda layer"
  value       = try(aws_lambda_layer_version.shared_deps[0].arn, "")
}

output "api_layer_arn" {
  description = "ARN of the API Lambda layer"
  value       = try(data.aws_lambda_layer_version.api_deps[0].arn, "")
}

output "orchestrator_layer_arn" {
  description = "ARN of the orchestrator Lambda layer"
  value       = try(data.aws_lambda_layer_version.orchestrator_deps[0].arn, "")
}
