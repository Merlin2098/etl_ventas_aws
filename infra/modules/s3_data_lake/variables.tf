variable "name_prefix" {
  description = "Naming prefix, e.g. <project_name>-<environment>."
  type        = string
}

variable "bucket_suffix" {
  description = "Suffix appended to the generated data lake bucket name."
  type        = string
  default     = "datalake"
}

variable "account_id" {
  description = "AWS account ID, used to keep the bucket name globally unique."
  type        = string
}

variable "force_destroy" {
  description = "Whether Terraform may destroy the bucket even when it contains objects."
  type        = bool
  default     = true
}

variable "divisions" {
  description = "RetailCorp divisions, one S3 notification filter per division."
  type        = list(string)
}

variable "lambda_function_arns" {
  description = "Lambda function ARN per division (from modules/lambda_ingestion), used to wire up bucket notifications."
  type        = map(string)
}

variable "lambda_permission_dependency" {
  description = "The aws_lambda_permission resources from modules/lambda_ingestion; passed in purely to sequence the notification after the permission exists."
  type        = any
  default     = null
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
}
