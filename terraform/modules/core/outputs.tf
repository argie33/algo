output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "ecr_repository_uri" {
  value = aws_ecr_repository.main.repository_url
}

output "cf_templates_bucket_name" {
  value = aws_s3_bucket.cf_templates.id
}

output "code_bucket_name" {
  value = aws_s3_bucket.code.id
}

output "algo_artifacts_bucket_name" {
  value = aws_s3_bucket.algo_artifacts.id
}

output "bastion_sg_id" {
  value = aws_security_group.bastion.id
}

output "vpce_sg_id" {
  value = aws_security_group.vpce.id
}

output "ecs_tasks_sg_id" {
  value = aws_security_group.ecs_tasks.id
}

output "rds_sg_id" {
  value = aws_security_group.rds.id
}
