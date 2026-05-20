# ============================================================
# Secrets Module - Input Variables
# ============================================================

variable "common_tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
}

# Alpaca Credentials
variable "alpaca_api_key" {
  description = "Alpaca API key ID for paper trading"
  type        = string
  sensitive   = true
}

variable "alpaca_api_secret" {
  description = "Alpaca API secret key for paper trading"
  type        = string
  sensitive   = true
}

# FRED Credentials
variable "fred_api_key" {
  description = "Federal Reserve Economic Data (FRED) API key"
  type        = string
  sensitive   = true
}

# Database Credentials
variable "db_host" {
  description = "PostgreSQL database hostname"
  type        = string
  sensitive   = true
}

variable "db_port" {
  description = "PostgreSQL database port"
  type        = number
  default     = 5432
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "stocks"
}

variable "db_user" {
  description = "PostgreSQL database user"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "PostgreSQL database password"
  type        = string
  sensitive   = true
}

# JWT Secret
variable "jwt_secret" {
  description = "Secret key for JWT token signing"
  type        = string
  sensitive   = true
}
