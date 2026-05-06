variable "project_name" {
  type = string
}

variable "github_org" {
  type = string
}

variable "github_repo" {
  type = string
}

variable "aws_account_id" {
  type      = string
  sensitive = true
}

variable "common_tags" {
  type = map(string)
}
