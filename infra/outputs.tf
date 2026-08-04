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

# --- Retail data lake demo (SPEC-004) ---

output "data_bucket_name" {
  description = "Name of the data lake bucket (bronze/gold/quarantine/athena-results)."
  value       = module.s3_data_lake.bucket_name
}

output "ecr_repository_urls" {
  description = "ECR repository URL per division."
  value       = module.ecr.repository_urls
}

output "lambda_function_arns" {
  description = "Ingestion Lambda function ARN per division."
  value       = module.lambda_ingestion.function_arns
}

output "lambda_log_group_names" {
  description = "Ingestion Lambda CloudWatch log group name per division."
  value       = module.lambda_ingestion.log_group_names
}

output "eventbridge_rule_names" {
  description = "EventBridge rule name per division, ingestion stage (bronze/ -> ingestion Lambda)."
  value       = module.eventbridge.rule_names
}

output "eventbridge_transform_rule_names" {
  description = "EventBridge rule name per division, transform stage (silver/ -> transform Lambda)."
  value       = module.eventbridge.transform_rule_names
}

output "glue_database_name" {
  description = "Glue Catalog database name."
  value       = module.glue_catalog.database_name
}

output "glue_crawler_name" {
  description = "Gold layer Glue Crawler name."
  value       = module.glue_catalog.crawler_name
}

output "athena_workgroup_name" {
  description = "Athena workgroup name."
  value       = module.athena.workgroup_name
}
