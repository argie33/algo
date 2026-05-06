variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "aws_account_id" {
  type      = string
  sensitive = true
}

variable "vpc_cidr" {
  type = string
}

variable "public_subnet_cidrs" {
  type = list(string)
}

variable "private_subnet_cidrs" {
  type = list(string)
}

variable "availability_zones" {
  type = list(string)
}

variable "notification_email" {
  type = string
}

variable "common_tags" {
  type = map(string)
}

variable "create_ecr_repository" {
  type    = bool
  default = false
}
