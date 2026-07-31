variable "project_name" {
  description = "Project name used in AWS resource naming."
  type        = string
  default     = "data-platform"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"
}

variable "owner" {
  description = "Owner tag applied to all managed resources."
  type        = string
  default     = "data-engineering"
}

variable "aws_region" {
  description = "AWS region for the deployment."
  type        = string
  default     = "us-east-1"
}

variable "artifact_path" {
  description = "Path to the packaged runtime artifact produced by make package."
  type        = string
  default     = "../artifacts/data_platform_bundle.zip"
}

variable "artifact_bucket_suffix" {
  description = "Suffix appended to the generated artifact bucket name."
  type        = string
  default     = "artifacts"
}

variable "artifact_bucket_force_destroy" {
  description = "Whether Terraform may destroy the artifact bucket even when it contains objects. Keep true for dev and sandbox environments."
  type        = bool
  default     = true
}

variable "enable_artifact_bucket_versioning" {
  description = "Whether to enable versioning on the artifact bucket. Defaults to false to keep dev environments cheap and easy to destroy."
  type        = bool
  default     = false
}

variable "execution_role_name" {
  description = "IAM role name for AWS data jobs."
  type        = string
  default     = "data-job-execution-role"
}

variable "tags" {
  description = "Additional tags applied to all resources."
  type        = map(string)
  default     = {}
}

variable "cost_center" {
  description = "Cost center tag for budget allocation and cost reporting."
  type        = string
  default     = "engineering"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days. Use 7 for demos and labs; set higher for production per compliance requirements."
  type        = number
  default     = 7
}

variable "budget_limit_usd" {
  description = "Monthly AWS budget limit in USD. Alerts fire at 80% (actual) and 100% (forecasted)."
  type        = number
  default     = 25
}

variable "budget_alert_email" {
  description = "Email address for budget alerts. Leave empty to skip SNS subscription creation."
  type        = string
  default     = ""
}
