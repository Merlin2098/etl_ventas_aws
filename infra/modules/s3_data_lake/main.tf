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

# AWS allows only one aws_s3_bucket_notification resource per bucket, so both
# pipeline stages' triggers live here: one dynamic block per division for the
# ingestion Lambda (filtered by the literal, static prefix bronze/<division>/
# — division comes before the variable date segment, which is what makes
# filter_prefix work at all), and one for the transform Lambda (filtered by
# silver/store=<division>/, SPEC-003/SPEC-004).
resource "aws_s3_bucket_notification" "data_lake_ingestion" {
  bucket = aws_s3_bucket.data_lake.id

  dynamic "lambda_function" {
    for_each = toset(var.divisions)
    content {
      lambda_function_arn = var.lambda_function_arns[lambda_function.value]
      events              = ["s3:ObjectCreated:*"]
      filter_prefix       = "bronze/${lambda_function.value}/"
    }
  }

  dynamic "lambda_function" {
    for_each = toset(var.divisions)
    content {
      lambda_function_arn = var.transform_lambda_function_arns[lambda_function.value]
      events              = ["s3:ObjectCreated:*"]
      filter_prefix       = "silver/store=${lambda_function.value}/"
    }
  }

  # AWS rejects the notification config if the Lambda's resource policy does
  # not yet grant s3.amazonaws.com permission to invoke it — this dependency
  # forces Terraform to create the permission first (Policy 010).
  depends_on = [var.lambda_permission_dependency]
}
