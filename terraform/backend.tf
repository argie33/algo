# ============================================================
# Root Module - Backend Configuration
# ============================================================

terraform {
  backend "s3" {
    bucket         = "stocks-terraform-state-dev"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "stocks-terraform-locks"
    encrypt        = true
  }

  # Alternative: use this backend for local testing
  # backend "local" {
  #   path = ".terraform/state/dev/terraform.tfstate"
  # }
}
