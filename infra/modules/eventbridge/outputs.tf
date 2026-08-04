output "rule_names" {
  description = "EventBridge rule name per division, ingestion stage."
  value       = { for division, rule in aws_cloudwatch_event_rule.ingestion : division => rule.name }
}

output "transform_rule_names" {
  description = "EventBridge rule name per division, transform stage."
  value       = { for division, rule in aws_cloudwatch_event_rule.transform : division => rule.name }
}

output "rule_arns" {
  description = "EventBridge rule ARN per division, ingestion stage."
  value       = { for division, rule in aws_cloudwatch_event_rule.ingestion : division => rule.arn }
}

output "transform_rule_arns" {
  description = "EventBridge rule ARN per division, transform stage."
  value       = { for division, rule in aws_cloudwatch_event_rule.transform : division => rule.arn }
}

# Policy 009 requires a resource_arn output per module. EventBridge rules do
# not produce their own CloudWatch log group — rule/target execution is
# recorded in the invoked Lambda's own log group, which already exists in
# modules/lambda_ingestion — so no log_group_name/log_group_arn output is
# declared here.
output "resource_arn" {
  description = "All EventBridge rule ARNs, both stages (Policy 009 required output)."
  value = concat(
    [for rule in aws_cloudwatch_event_rule.ingestion : rule.arn],
    [for rule in aws_cloudwatch_event_rule.transform : rule.arn],
  )
}
