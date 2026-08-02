variable "name_prefix" {
  description = "Naming prefix, e.g. <project_name>-<environment>."
  type        = string
}

variable "divisions" {
  description = "RetailCorp divisions, one Lambda function per division."
  type        = list(string)
}

variable "ecr_repository_urls" {
  description = "ECR repository URL per division (from modules/ecr)."
  type        = map(string)
}

variable "lambda_image_tag" {
  description = "Image tag/digest to deploy per division. Never 'latest' (SPEC-004/SPEC-005)."
  type        = map(string)
}

variable "data_bucket_name" {
  description = "Name of the S3 data lake bucket (bronze/gold/quarantine)."
  type        = string
}

variable "data_bucket_arn" {
  description = "ARN of the S3 data lake bucket."
  type        = string
}

variable "gold_prefix" {
  description = "Base prefix for the Gold layer."
  type        = string
  default     = "gold/"
}

variable "quarantine_prefix" {
  description = "Base prefix for the Quarantine layer."
  type        = string
  default     = "quarantine/"
}

variable "lambda_memory_size" {
  description = "Memory (MB) allocated to each Lambda function."
  type        = number
  default     = 512
}

variable "lambda_timeout" {
  description = "Timeout (seconds) for each Lambda function."
  type        = number
  default     = 60
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days for each Lambda's log group."
  type        = number
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
}
