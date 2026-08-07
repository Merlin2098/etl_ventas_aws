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

# Least-privilege per division: read bronze/date=*/<division>/ (Bronze is
# date-partitioned first, division second — see SPEC-003), write silver/ +
# quarantine/ (both are division-partitioned so a single statement per
# division covers only its own partition), and logs scoped to its own log
# group.
data "aws_iam_policy_document" "division" {
  for_each = toset(var.divisions)

  statement {
    sid       = "ReadOwnBronzePrefix"
    actions   = ["s3:GetObject"]
    resources = ["${var.data_bucket_arn}/bronze/date=*/${each.key}/*"]
  }

  statement {
    sid = "WriteOwnSilverAndQuarantinePartitions"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      "${var.data_bucket_arn}/${var.silver_prefix}store=${each.key}/*",
      "${var.data_bucket_arn}/${var.quarantine_prefix}store=${each.key}/*",
    ]
  }

  statement {
    sid       = "ListOwnSilverPartitionForDeleteThenWrite"
    actions   = ["s3:ListBucket"]
    resources = [var.data_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.silver_prefix}store=${each.key}/*"]
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
      SILVER_PREFIX     = var.silver_prefix
      QUARANTINE_PREFIX = var.quarantine_prefix
      LOG_LEVEL         = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.division]

  tags = var.tags
}

# --- Transform Lambda (Silver -> Gold), one per division, mirroring the
# ingestion resources above. Reuses the ingestion Lambda's own image (no
# separate ECR repo/build): `transform/handler.py` is generic, not tied to a
# source format, so the only difference from the ingestion function is the
# image_config.command override below (see SPEC-005 "Uso de Docker y ECR").

resource "aws_iam_role" "division_transform" {
  for_each = toset(var.divisions)

  name               = "${var.name_prefix}-lambda-${each.key}-transform-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_cloudwatch_log_group" "division_transform" {
  for_each = toset(var.divisions)

  name              = "/aws/lambda/${var.name_prefix}-transform-${each.key}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# Least-privilege per division: read silver/store=<division>/, write gold/ +
# quarantine/ (same partitions the ingestion Lambda's policy already covers
# for writing, now written from the other side of the pipeline).
data "aws_iam_policy_document" "division_transform" {
  for_each = toset(var.divisions)

  statement {
    sid       = "ReadOwnSilverPrefix"
    actions   = ["s3:GetObject"]
    resources = ["${var.data_bucket_arn}/${var.silver_prefix}store=${each.key}/*"]
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
    resources = ["${aws_cloudwatch_log_group.division_transform[each.key].arn}:*"]
  }
}

resource "aws_iam_role_policy" "division_transform" {
  for_each = toset(var.divisions)

  name   = "${var.name_prefix}-lambda-${each.key}-transform-policy"
  role   = aws_iam_role.division_transform[each.key].id
  policy = data.aws_iam_policy_document.division_transform[each.key].json
}

resource "aws_lambda_function" "division_transform" {
  for_each = toset(var.divisions)

  function_name = "${var.name_prefix}-transform-${each.key}"
  package_type  = "Image"
  image_uri     = "${var.ecr_repository_urls[each.key]}:${var.lambda_image_tag[each.key]}"
  role          = aws_iam_role.division_transform[each.key].arn

  image_config {
    command = ["lambda_ingestion.transform.handler.handler"]
  }

  memory_size = var.lambda_memory_size
  timeout     = var.lambda_timeout

  environment {
    variables = {
      DIVISION          = each.key
      DATA_BUCKET       = var.data_bucket_name
      SILVER_PREFIX     = var.silver_prefix
      GOLD_PREFIX       = var.gold_prefix
      QUARANTINE_PREFIX = var.quarantine_prefix
      LOG_LEVEL         = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.division_transform]

  tags = var.tags
}
