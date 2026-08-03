data "aws_caller_identity" "current" {}

locals {
  name_prefix  = lower(replace("${var.project_name}-${var.environment}", "_", "-"))
  bucket_name  = "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-${var.artifact_bucket_suffix}"
  artifact_key = "packages/${basename(var.artifact_path)}"
  common_tags = merge(
    var.tags,
    {
      Project     = var.project_name
      Environment = var.environment
      Owner       = var.owner
      ManagedBy   = "Terraform"
      CostCenter  = var.cost_center
    }
  )

  # Computed the same way as modules/s3_data_lake's internal bucket name, so
  # lambda_ingestion can receive the bucket name/ARN as plain strings without
  # depending on the aws_s3_bucket resource itself (which in turn depends on
  # lambda_ingestion for its notification ARNs — see module dependency order
  # below). This avoids a circular module dependency.
  data_bucket_name = "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-datalake"
  data_bucket_arn  = "arn:aws:s3:::${local.data_bucket_name}"
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = local.bucket_name
  force_destroy = var.artifact_bucket_force_destroy
  tags          = local.common_tags
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = var.enable_artifact_bucket_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.bucket

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "artifact_bundle" {
  bucket = aws_s3_bucket.artifacts.id
  key    = local.artifact_key
  source = var.artifact_path
  etag   = filemd5(var.artifact_path)
  tags   = local.common_tags
}

data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "data_job_execution" {
  name               = "${local.name_prefix}-${var.execution_role_name}"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "glue_service_role" {
  role       = aws_iam_role.data_job_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "artifact_access" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.artifacts.arn}/*"]
  }

  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]
  }
}

resource "aws_iam_role_policy" "artifact_access" {
  name   = "${local.name_prefix}-artifact-access"
  role   = aws_iam_role.data_job_execution.id
  policy = data.aws_iam_policy_document.artifact_access.json
}

resource "aws_cloudwatch_log_group" "data_jobs" {
  name              = "/aws/data-jobs/${local.name_prefix}"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

data "aws_iam_policy_document" "cloudwatch_logs_access" {
  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = ["${aws_cloudwatch_log_group.data_jobs.arn}:*"]
  }
}

resource "aws_iam_role_policy" "cloudwatch_logs_access" {
  name   = "${local.name_prefix}-cloudwatch-logs-access"
  role   = aws_iam_role.data_job_execution.id
  policy = data.aws_iam_policy_document.cloudwatch_logs_access.json
}

resource "aws_sns_topic" "budget_alerts" {
  count = var.budget_alert_email != "" ? 1 : 0
  name  = "${local.name_prefix}-budget-alerts"
  tags  = local.common_tags
}

resource "aws_sns_topic_subscription" "budget_email" {
  count     = var.budget_alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.budget_alerts[0].arn
  protocol  = "email"
  endpoint  = var.budget_alert_email
}

# --- Retail data lake demo (SPEC-004) ---
# Deployment order: ecr -> lambda_ingestion -> s3_data_lake -> glue_catalog -> athena.
# `ecr` must exist and be populated (scripts/docker_push.sh) before the first
# apply that creates `lambda_ingestion`, since aws_lambda_function with
# package_type = "Image" requires the image to already exist in ECR.

module "ecr" {
  source = "./modules/ecr"

  name_prefix = local.name_prefix
  divisions   = var.divisions
  tags        = local.common_tags
}

module "lambda_ingestion" {
  source = "./modules/lambda_ingestion"

  name_prefix         = local.name_prefix
  divisions           = var.divisions
  ecr_repository_urls = module.ecr.repository_urls
  lambda_image_tag    = var.lambda_image_tag
  data_bucket_name    = local.data_bucket_name
  data_bucket_arn     = local.data_bucket_arn
  lambda_memory_size  = var.lambda_memory_size
  lambda_timeout      = var.lambda_timeout
  log_retention_days  = var.log_retention_days
  tags                = local.common_tags
}

module "s3_data_lake" {
  source = "./modules/s3_data_lake"

  name_prefix                    = local.name_prefix
  account_id                     = data.aws_caller_identity.current.account_id
  force_destroy                  = var.data_bucket_force_destroy
  divisions                      = var.divisions
  lambda_function_arns           = module.lambda_ingestion.function_arns
  transform_lambda_function_arns = module.lambda_ingestion.transform_function_arns
  lambda_permission_dependency = merge(
    module.lambda_ingestion.function_names,
    module.lambda_ingestion.transform_function_names,
  )
  tags = local.common_tags
}

module "glue_catalog" {
  source = "./modules/glue_catalog"

  name_prefix      = local.name_prefix
  data_bucket_name = module.s3_data_lake.bucket_name
  data_bucket_arn  = module.s3_data_lake.bucket_arn
  crawler_schedule = var.glue_crawler_schedule
  tags             = local.common_tags
}

module "athena" {
  source = "./modules/athena"

  name_prefix      = local.name_prefix
  data_bucket_name = module.s3_data_lake.bucket_name
  tags             = local.common_tags
}

resource "aws_budgets_budget" "monthly" {
  name              = "${local.name_prefix}-monthly-budget"
  budget_type       = "COST"
  limit_amount      = tostring(var.budget_limit_usd)
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "2024-01-01_00:00"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Project$${var.project_name}"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.budget_alert_email != "" ? [var.budget_alert_email] : []
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.budget_alert_email != "" ? [var.budget_alert_email] : []
  }
}
