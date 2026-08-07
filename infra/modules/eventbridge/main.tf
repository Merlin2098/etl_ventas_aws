# Routes S3 ObjectCreated events (delivered to the default EventBridge bus by
# modules/s3_data_lake's aws_s3_bucket_notification with eventbridge = true)
# to the ingestion and transform Lambdas. Rule, target and lambda:InvokeFunction
# permission live together in this module (Policy 010): the permission needs
# the rule's own ARN, which only exists here, so placing it in
# modules/lambda_ingestion (as the old S3-notification permission did) would
# recreate the circular-dependency problem Policy 010 exists to avoid — this
# time in the opposite direction, since the determining ARN is now the rule's,
# not the Lambda's (SPEC-003/SPEC-004).
resource "aws_cloudwatch_event_rule" "ingestion" {
  for_each = toset(var.divisions)

  name        = "${var.name_prefix}-ingestion-${each.key}"
  description = "Objetos nuevos en bronze/date=*/${each.key}/ -> Lambda de ingesta"

  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [var.data_bucket_name] }
      object = { key = [{ wildcard = "bronze/date=*/${each.key}/*" }] }
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "ingestion" {
  for_each = toset(var.divisions)

  rule      = aws_cloudwatch_event_rule.ingestion[each.key].name
  target_id = "ingestion-${each.key}"
  arn       = var.lambda_function_arns[each.key]
}

resource "aws_lambda_permission" "allow_eventbridge_ingestion" {
  for_each = toset(var.divisions)

  statement_id  = "AllowEventBridgeInvokeIngestion"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_names[each.key]
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingestion[each.key].arn
}

resource "aws_cloudwatch_event_rule" "transform" {
  for_each = toset(var.divisions)

  name        = "${var.name_prefix}-transform-${each.key}"
  description = "Objetos nuevos en silver/store=${each.key}/ -> Lambda de transformacion"

  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [var.data_bucket_name] }
      object = { key = [{ prefix = "silver/store=${each.key}/" }] }
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "transform" {
  for_each = toset(var.divisions)

  rule      = aws_cloudwatch_event_rule.transform[each.key].name
  target_id = "transform-${each.key}"
  arn       = var.transform_lambda_function_arns[each.key]
}

resource "aws_lambda_permission" "allow_eventbridge_transform" {
  for_each = toset(var.divisions)

  statement_id  = "AllowEventBridgeInvokeTransform"
  action        = "lambda:InvokeFunction"
  function_name = var.transform_lambda_function_names[each.key]
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.transform[each.key].arn
}
