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
  value = concat(
    [for fn in aws_lambda_function.division : fn.arn],
    [for fn in aws_lambda_function.division_transform : fn.arn],
  )
}

output "transform_function_arns" {
  description = "Transform Lambda function ARN per division (Silver -> Gold)."
  value       = { for division, fn in aws_lambda_function.division_transform : division => fn.arn }
}

output "transform_function_names" {
  description = "Transform Lambda function name per division."
  value       = { for division, fn in aws_lambda_function.division_transform : division => fn.function_name }
}

output "transform_log_group_names" {
  description = "CloudWatch log group name per division for the transform Lambda."
  value       = { for division, lg in aws_cloudwatch_log_group.division_transform : division => lg.name }
}

output "transform_log_group_arns" {
  description = "CloudWatch log group ARN per division for the transform Lambda."
  value       = { for division, lg in aws_cloudwatch_log_group.division_transform : division => lg.arn }
}
