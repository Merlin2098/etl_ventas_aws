output "workgroup_name" {
  description = "Athena workgroup name."
  value       = aws_athena_workgroup.this.name
}

output "resource_arn" {
  description = "Athena workgroup ARN (Policy 009 required output)."
  value       = aws_athena_workgroup.this.arn
}
