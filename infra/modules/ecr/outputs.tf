output "repository_urls" {
  description = "ECR repository URL per division."
  value       = { for division, repo in aws_ecr_repository.division : division => repo.repository_url }
}

output "repository_arns" {
  description = "ECR repository ARN per division."
  value       = { for division, repo in aws_ecr_repository.division : division => repo.arn }
}
