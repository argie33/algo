output "trigger_loaders_lambda_arn" {
  description = "ARN of the trigger loaders Lambda function"
  value       = aws_lambda_function.trigger_loaders.arn
}

output "trigger_loaders_lambda_name" {
  description = "Name of the trigger loaders Lambda function"
  value       = aws_lambda_function.trigger_loaders.function_name
}
