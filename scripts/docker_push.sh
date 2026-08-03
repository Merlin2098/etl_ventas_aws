#!/usr/bin/env bash
set -euo pipefail

# Builds and pushes the 4 division Lambda images from the single
# docker/Dockerfile (SPEC-005 / SPEC-004 "Flujo de despliegue"). Each image
# serves both Lambda functions of its division (ingestion + transform,
# SPEC-004/SPEC-005) — the transform function overrides the entrypoint via
# Terraform's image_config.command, no separate build needed. Requires the
# ECR repositories to already exist (first `terraform apply`, SPEC-004).

DIVISIONS=(electronica supermercado moda marketplace)
IMAGE_TAG=$(git rev-parse --short HEAD)
REGION="${AWS_REGION:-us-east-1}"

TMP_DOCKERFILE=$(mktemp)
trap 'rm -f "$TMP_DOCKERFILE"' EXIT

for DIVISION in "${DIVISIONS[@]}"; do
  REPO_URL=$(terraform -chdir=infra output -json ecr_repository_urls | python3 -c "import json,sys; print(json.load(sys.stdin)['$DIVISION'])")

  # CMD in Lambda images must use exec form, which Docker does not
  # variable-substitute at build time — resolve the __DIVISION__ placeholder
  # here before building (see docker/Dockerfile header comment).
  sed "s/__DIVISION__/${DIVISION}/g" docker/Dockerfile > "$TMP_DOCKERFILE"

  echo "Building ${DIVISION} -> ${REPO_URL}:${IMAGE_TAG}"
  docker build \
    --platform linux/amd64 \
    --provenance=false \
    --build-arg DIVISION="${DIVISION}" \
    --file "$TMP_DOCKERFILE" \
    -t "${REPO_URL}:${IMAGE_TAG}" \
    .

  aws ecr get-login-password --region "$REGION" | \
    docker login --username AWS --password-stdin "$REPO_URL"

  docker push "${REPO_URL}:${IMAGE_TAG}"
  echo "Pushed ${REPO_URL}:${IMAGE_TAG}"
done

echo ""
echo "All images pushed with tag: ${IMAGE_TAG}"
echo "Update terraform.tfvars: lambda_image_tag = { electronica = \"${IMAGE_TAG}\", supermercado = \"${IMAGE_TAG}\", moda = \"${IMAGE_TAG}\", marketplace = \"${IMAGE_TAG}\" }"
