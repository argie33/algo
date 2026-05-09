# ============================================================
# VPC Module - Outputs
# ============================================================

# VPC
output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.main.cidr_block
}

# Public Subnets
output "public_subnet_ids" {
  description = "IDs of public subnets (one per AZ)"
  value       = aws_subnet.public[*].id
}

output "public_subnet_cidrs" {
  description = "CIDR blocks of public subnets"
  value       = aws_subnet.public[*].cidr_block
}

# Private Subnets
output "private_subnet_ids" {
  description = "IDs of private subnets (one per AZ)"
  value       = aws_subnet.private[*].id
}

output "private_subnet_cidrs" {
  description = "CIDR blocks of private subnets"
  value       = aws_subnet.private[*].cidr_block
}

# Security Groups
output "bastion_security_group_id" {
  description = "ID of bastion security group"
  value       = var.bastion_sg_enabled ? aws_security_group.bastion[0].id : null
}

output "ecs_tasks_security_group_id" {
  description = "ID of ECS tasks security group"
  value       = aws_security_group.ecs_tasks.id
}

output "api_lambda_security_group_id" {
  description = "ID of API Lambda security group (dedicated for REST API Lambda)"
  value       = aws_security_group.api_lambda.id
}

output "algo_lambda_security_group_id" {
  description = "ID of Algo Lambda security group (dedicated for orchestrator Lambda)"
  value       = aws_security_group.algo_lambda.id
}

output "rds_security_group_id" {
  description = "ID of RDS security group"
  value       = aws_security_group.rds.id
}

output "vpc_endpoints_security_group_id" {
  description = "ID of VPC endpoints security group"
  value       = aws_security_group.vpc_endpoints.id
}

# VPC Endpoints (for policies that need to reference them)
output "s3_endpoint_id" {
  description = "ID of S3 gateway endpoint"
  value       = aws_vpc_endpoint.s3.id
}

output "dynamodb_endpoint_id" {
  description = "ID of DynamoDB gateway endpoint"
  value       = aws_vpc_endpoint.dynamodb.id
}

output "secretsmanager_endpoint_id" {
  description = "ID of Secrets Manager interface endpoint"
  value       = aws_vpc_endpoint.secretsmanager.id
}

output "ecr_api_endpoint_id" {
  description = "ID of ECR API interface endpoint"
  value       = aws_vpc_endpoint.ecr_api.id
}

output "ecr_dkr_endpoint_id" {
  description = "ID of ECR DKR interface endpoint"
  value       = aws_vpc_endpoint.ecr_dkr.id
}

output "logs_endpoint_id" {
  description = "ID of CloudWatch Logs interface endpoint"
  value       = aws_vpc_endpoint.logs.id
}

output "sns_endpoint_id" {
  description = "ID of SNS interface endpoint"
  value       = aws_vpc_endpoint.sns.id
}
