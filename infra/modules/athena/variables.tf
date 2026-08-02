variable "name_prefix" {
  description = "Naming prefix, e.g. <project_name>-<environment>."
  type        = string
}

variable "data_bucket_name" {
  description = "Name of the S3 data lake bucket, used for the query results prefix."
  type        = string
}

variable "results_prefix" {
  description = "Prefix within the data bucket for Athena query results."
  type        = string
  default     = "athena-results/"
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
}
