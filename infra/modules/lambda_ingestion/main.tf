data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "division" {
  for_each = toset(var.divisions)

  name               = "${var.name_prefix}-lambda-${each.key}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_cloudwatch_log_group" "division" {
  for_each = toset(var.divisions)

  name              = "/aws/lambda/${var.name_prefix}-ingestion-${each.key}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# Least-privilege per division: read bronze/<division>/, write gold/ + quarantine/
# (both are division-partitioned so a single statement per division covers only
# its own partition), and logs scoped to its own log group.
data "aws_iam_policy_document" "division" {
  for_each = toset(var.divisions)

  statement {
    sid       = "ReadOwnBronzePrefix"
    actions   = ["s3:GetObject"]
    resources = ["${var.data_bucket_arn}/bronze/${each.key}/*"]
  }

  statement {
    sid = "WriteOwnGoldAndQuarantinePartitions"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      "${var.data_bucket_arn}/${var.gold_prefix}store=${each.key}/*",
      "${var.data_bucket_arn}/${var.quarantine_prefix}store=${each.key}/*",
    ]
  }

  statement {
    sid       = "ListOwnGoldPartitionForDeleteThenWrite"
    actions   = ["s3:ListBucket"]
    resources = [var.data_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.gold_prefix}store=${each.key}/*"]
    }
  }

  statement {
    sid = "OwnLogGroup"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.division[each.key].arn}:*"]
  }
}

resource "aws_iam_role_policy" "division" {
  for_each = toset(var.divisions)

  name   = "${var.name_prefix}-lambda-${each.key}-policy"
  role   = aws_iam_role.division[each.key].id
  policy = data.aws_iam_policy_document.division[each.key].json
}

resource "aws_lambda_function" "division" {
  for_each = toset(var.divisions)

  function_name = "${var.name_prefix}-ingestion-${each.key}"
  package_type  = "Image"
  image_uri     = "${var.ecr_repository_urls[each.key]}:${var.lambda_image_tag[each.key]}"
  role          = aws_iam_role.division[each.key].arn

  memory_size = var.lambda_memory_size
  timeout     = var.lambda_timeout

  environment {
    variables = {
      DIVISION          = each.key
      DATA_BUCKET       = var.data_bucket_name
      GOLD_PREFIX       = var.gold_prefix
      QUARANTINE_PREFIX = var.quarantine_prefix
      LOG_LEVEL         = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.division]

  tags = var.tags
}

# Policy 010 (IAM cross-module placement): the Lambda ARN lives in this
# module, so the permission that lets S3 invoke it is declared here, not in
# modules/s3_data_lake (which only receives these ARNs as an input variable).
resource "aws_lambda_permission" "allow_s3_invoke" {
  for_each = toset(var.divisions)

  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.division[each.key].function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.data_bucket_arn
}
