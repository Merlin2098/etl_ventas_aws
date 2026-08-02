output "bucket_name" {
  description = "Name of the data lake bucket (bronze/gold/quarantine/athena-results)."
  value       = aws_s3_bucket.data_lake.bucket
}

output "bucket_arn" {
  description = "ARN of the data lake bucket."
  value       = aws_s3_bucket.data_lake.arn
}

output "resource_arn" {
  description = "Bucket ARN (Policy 009 required output)."
  value       = aws_s3_bucket.data_lake.arn
}
