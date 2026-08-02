resource "aws_ecr_repository" "division" {
  for_each = toset(var.divisions)

  name         = "${var.name_prefix}-${each.key}"
  force_delete = true # demo/ephemeral environment (SPEC-004 "Flujo de destrucción")

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "division" {
  for_each = aws_ecr_repository.division

  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 }
      action       = { type = "expire" }
    }]
  })
}
