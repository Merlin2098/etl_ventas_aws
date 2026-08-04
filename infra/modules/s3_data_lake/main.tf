locals {
  bucket_name = "${var.name_prefix}-${var.account_id}-${var.bucket_suffix}"
}

resource "aws_s3_bucket" "data_lake" {
  bucket        = local.bucket_name
  force_destroy = var.force_destroy
  tags          = var.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.bucket

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Routes every ObjectCreated event on this bucket to the account's default
# EventBridge bus instead of invoking Lambdas directly (see modules/eventbridge,
# which owns the rules, targets and lambda:InvokeFunction permissions for both
# pipeline stages — SPEC-003/SPEC-004).
resource "aws_s3_bucket_notification" "data_lake" {
  bucket      = aws_s3_bucket.data_lake.id
  eventbridge = true
}
