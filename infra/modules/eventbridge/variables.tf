variable "name_prefix" {
  description = "Naming prefix, e.g. <project_name>-<environment>."
  type        = string
}

variable "divisions" {
  description = "RetailCorp divisions, one EventBridge rule per division and per stage."
  type        = list(string)
}

variable "data_bucket_name" {
  description = "Name of the data lake bucket (from modules/s3_data_lake), matched in the event_pattern of every rule."
  type        = string
}

variable "lambda_function_arns" {
  description = "Ingestion Lambda function ARN per division (from modules/lambda_ingestion), used as the EventBridge target."
  type        = map(string)
}

variable "lambda_function_names" {
  description = "Ingestion Lambda function name per division, used to scope the lambda:InvokeFunction permission."
  type        = map(string)
}

variable "transform_lambda_function_arns" {
  description = "Transform Lambda function ARN per division (from modules/lambda_ingestion), used as the EventBridge target."
  type        = map(string)
}

variable "transform_lambda_function_names" {
  description = "Transform Lambda function name per division, used to scope the lambda:InvokeFunction permission."
  type        = map(string)
}

variable "tags" {
  description = "Common tags applied to all resources."
  type        = map(string)
}
