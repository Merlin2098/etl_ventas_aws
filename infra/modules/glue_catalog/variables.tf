variable "name_prefix" {
  description = "Naming prefix, e.g. <project_name>-<environment>."
  type        = string
}

variable "data_bucket_name" {
  description = "Name of the S3 data lake bucket."
  type        = string
}

variable "data_bucket_arn" {
  description = "ARN of the S3 data lake bucket."
  type        = string
}

variable "gold_prefix" {
  description = "Base prefix for the Gold layer, crawled to discover the sales table."
  type        = string
  default     = "gold/"
}

variable "crawler_schedule" {
  description = "Cron expression for the Crawler. Empty string = manual execution only (SPEC-004/SPEC-006)."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
}
