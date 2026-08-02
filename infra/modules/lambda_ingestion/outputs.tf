output "function_arns" {
  description = "Lambda function ARN per division."
  value       = { for division, fn in aws_lambda_function.division : division => fn.arn }
}

output "function_names" {
  description = "Lambda function name per division."
  value       = { for division, fn in aws_lambda_function.division : division => fn.function_name }
}

output "log_group_names" {
  description = "CloudWatch log group name per division."
  value       = { for division, lg in aws_cloudwatch_log_group.division : division => lg.name }
}

output "log_group_arns" {
  description = "CloudWatch log group ARN per division."
  value       = { for division, lg in aws_cloudwatch_log_group.division : division => lg.arn }
}

output "resource_arn" {
  description = "All Lambda function ARNs (Policy 009 required output)."
  value       = [for fn in aws_lambda_function.division : fn.arn]
}
