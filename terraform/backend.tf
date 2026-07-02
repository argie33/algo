terraform {
  backend "s3" {
    bucket         = "stocks-terraform-state"
    key            = "stocks/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "stocks-terraform-locks"
  }
}
