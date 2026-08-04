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

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
}
