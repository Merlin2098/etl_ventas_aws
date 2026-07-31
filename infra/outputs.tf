output "artifact_bucket_name" {
  description = "S3 bucket used for packaged runtime artifacts."
  value       = aws_s3_bucket.artifacts.bucket
}

output "artifact_bundle_s3_uri" {
  description = "S3 URI of the packaged runtime artifact."
  value       = "s3://${aws_s3_bucket.artifacts.bucket}/${aws_s3_object.artifact_bundle.key}"
}

output "data_job_execution_role_arn" {
  description = "IAM role ARN for Glue or other batch data jobs."
  value       = aws_iam_role.data_job_execution.arn
}

output "log_group_name" {
  description = "CloudWatch log group name for data jobs."
  value       = aws_cloudwatch_log_group.data_jobs.name
}

output "log_group_arn" {
  description = "CloudWatch log group ARN for data jobs."
  value       = aws_cloudwatch_log_group.data_jobs.arn
}

output "budget_name" {
  description = "AWS Budget name for monthly cost governance."
  value       = aws_budgets_budget.monthly.name
}

output "budget_alert_sns_arn" {
  description = "SNS topic ARN for budget alerts. Empty string when no alert email is configured."
  value       = var.budget_alert_email != "" ? aws_sns_topic.budget_alerts[0].arn : ""
}
