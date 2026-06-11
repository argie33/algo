# C-7 FIX: CloudWatch alarms for Cognito client ID mismatches
# Detects: (1) "Token client mismatch" in logs, (2) Cognito misconfiguration, (3) API health check failures
# Assumes: SNS topic aws_sns_topic.algo_alerts already exists in services module

# Reference the CloudWatch log group created for API Lambda
# The log group is automatically created by Lambda; we just reference it here
locals {
  api_lambda_log_group = "/aws/lambda/algo-api-${var.environment}"
}

# Metric filter: Detect JWT client_id/aud claim mismatches
resource "aws_cloudwatch_log_group_metric_filter" "jwt_client_mismatch" {
  name           = "/algo/jwt-client-mismatch"
  log_group_name = local.api_lambda_log_group
  filter_pattern = "[..., \"Token client mismatch\"]"

  metric_transformation {
    name      = "JWTClientMismatchCount"
    namespace = "AlgoAPI"
    value     = "1"
  }
}

# Metric filter: Detect COGNITO_CLIENT_ID missing
resource "aws_cloudwatch_log_group_metric_filter" "cognito_misconfigured" {
  name           = "/algo/cognito-misconfigured"
  log_group_name = local.api_lambda_log_group
  filter_pattern = "[..., \"FATAL: COGNITO_CLIENT_ID not configured\"]"

  metric_transformation {
    name      = "CognitoMisconfiguredCount"
    namespace = "AlgoAPI"
    value     = "1"
  }
}

# Metric filter: Detect health check failures
resource "aws_cloudwatch_log_group_metric_filter" "health_cognito_failure" {
  name           = "/algo/health-cognito-failure"
  log_group_name = local.api_lambda_log_group
  filter_pattern = "[..., \"CRITICAL: COGNITO_CLIENT_ID\", \"not found in user pool\"]"

  metric_transformation {
    name      = "HealthCognitoFailureCount"
    namespace = "AlgoAPI"
    value     = "1"
  }
}

# Alarm: JWT client mismatch (fire immediately - indicates auth bypass)
resource "aws_cloudwatch_metric_alarm" "jwt_client_mismatch" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "algo-api-jwt-client-mismatch-${var.environment}"
  comparison_operator = "GreaterThanOrEqualTo"
  evaluation_periods  = "1"
  metric_name         = "JWTClientMismatchCount"
  namespace           = "AlgoAPI"
  period              = "60"
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "C-7 FIX: JWT client_id claim does not match COGNITO_CLIENT_ID configuration. This indicates Cognito or Lambda env vars are misconfigured. Users will be denied access."
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  treat_missing_data  = "notBreaching"

  depends_on = [aws_cloudwatch_log_group_metric_filter.jwt_client_mismatch]
}

# Alarm: Cognito misconfigured (fire immediately)
resource "aws_cloudwatch_metric_alarm" "cognito_misconfigured" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "algo-api-cognito-misconfigured-${var.environment}"
  comparison_operator = "GreaterThanOrEqualTo"
  evaluation_periods  = "1"
  metric_name         = "CognitoMisconfiguredCount"
  namespace           = "AlgoAPI"
  period              = "60"
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "C-7 FIX: COGNITO_CLIENT_ID or COGNITO_USER_POOL_ID environment variable is missing. Lambda authentication disabled. This is a critical deployment error."
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  treat_missing_data  = "notBreaching"

  depends_on = [aws_cloudwatch_log_group_metric_filter.cognito_misconfigured]
}

# Alarm: Health check Cognito failure (fire immediately)
resource "aws_cloudwatch_metric_alarm" "health_cognito_failure" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "algo-api-health-cognito-failure-${var.environment}"
  comparison_operator = "GreaterThanOrEqualTo"
  evaluation_periods  = "1"
  metric_name         = "HealthCognitoFailureCount"
  namespace           = "AlgoAPI"
  period              = "60"
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "C-7 FIX: /health/cognito endpoint detected that COGNITO_CLIENT_ID does not match Cognito user pool configuration. All JWT validations will fail, locking users out."
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  treat_missing_data  = "notBreaching"

  depends_on = [aws_cloudwatch_log_group_metric_filter.health_cognito_failure]
}
