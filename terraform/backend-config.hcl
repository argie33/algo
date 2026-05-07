bucket         = "terraform-state"
key            = "stocks/terraform.tfstate"
region         = "us-east-1"
encrypt        = true
dynamodb_table = "terraform-lock"
