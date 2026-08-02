output "database_name" {
  description = "Glue Catalog database name."
  value       = aws_glue_catalog_database.this.name
}

output "crawler_name" {
  description = "Glue Crawler name."
  value       = aws_glue_crawler.gold.name
}

output "log_group_name" {
  description = "Crawler CloudWatch log group name."
  value       = aws_cloudwatch_log_group.crawler.name
}

output "log_group_arn" {
  description = "Crawler CloudWatch log group ARN."
  value       = aws_cloudwatch_log_group.crawler.arn
}

output "resource_arn" {
  description = "Glue database ARN (Policy 009 required output)."
  value       = aws_glue_catalog_database.this.arn
}
