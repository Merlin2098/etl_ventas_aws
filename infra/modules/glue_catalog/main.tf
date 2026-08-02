resource "aws_glue_catalog_database" "this" {
  name = "${replace(var.name_prefix, "-", "_")}_catalog"
  tags = var.tags
}

data "aws_iam_policy_document" "crawler_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "crawler" {
  name               = "${var.name_prefix}-glue-crawler-role"
  assume_role_policy = data.aws_iam_policy_document.crawler_assume_role.json
  tags               = var.tags
}

data "aws_iam_policy_document" "crawler" {
  statement {
    sid       = "ReadGoldPrefix"
    actions   = ["s3:GetObject"]
    resources = ["${var.data_bucket_arn}/${var.gold_prefix}*"]
  }

  statement {
    sid       = "ListDataBucket"
    actions   = ["s3:ListBucket"]
    resources = [var.data_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.gold_prefix}*"]
    }
  }

  statement {
    sid = "GlueCatalogWrite"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:GetPartitions",
      "glue:BatchCreatePartition",
      "glue:BatchUpdatePartition",
    ]
    resources = [
      aws_glue_catalog_database.this.arn,
      "arn:aws:glue:*:*:catalog",
      "${aws_glue_catalog_database.this.arn}/*",
      replace(aws_glue_catalog_database.this.arn, ":database/", ":table/"),
      "${replace(aws_glue_catalog_database.this.arn, ":database/", ":table/")}/*",
    ]
  }

  statement {
    sid = "CrawlerLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:log-group:/aws-glue/crawlers*"]
  }
}

resource "aws_iam_role_policy" "crawler" {
  name   = "${var.name_prefix}-glue-crawler-policy"
  role   = aws_iam_role.crawler.id
  policy = data.aws_iam_policy_document.crawler.json
}

resource "aws_cloudwatch_log_group" "crawler" {
  name              = "/aws-glue/crawlers/${var.name_prefix}-gold-crawler"
  retention_in_days = 7
  tags              = var.tags
}

# No aws_glue_catalog_table is declared: the schema and store/date partitions
# are discovered by the crawler (SPEC-006 "Tablas" — a single explicit table
# would need to be kept in sync with the pyarrow GOLD_SCHEMA by hand).
resource "aws_glue_crawler" "gold" {
  name          = "${var.name_prefix}-gold-crawler"
  role          = aws_iam_role.crawler.arn
  database_name = aws_glue_catalog_database.this.name
  schedule      = var.crawler_schedule != "" ? var.crawler_schedule : null

  s3_target {
    path = "s3://${var.data_bucket_name}/${var.gold_prefix}"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  tags = var.tags
}
