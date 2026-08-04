#!/usr/bin/env bash
set -euo pipefail

# Publishes the 4 division Lambda images built by scripts/docker_build.sh to
# their ECR repositories (SPEC-005 / SPEC-004 "Flujo de despliegue"). Requires
# the ECR repositories to already exist (first `terraform apply`, SPEC-004)
# and AWS credentials valid for `aws ecr get-login-password`.

DIVISIONS=(electronica supermercado moda marketplace)
IMAGE_TAG=$(git rev-parse --short HEAD)
ECR_REGISTRY_PLACEHOLDER="local-build"
REGION="${AWS_REGION:-us-east-1}"

for DIVISION in "${DIVISIONS[@]}"; do
  LOCAL_IMAGE="${ECR_REGISTRY_PLACEHOLDER}/${DIVISION}:${IMAGE_TAG}"
  if ! docker image inspect "$LOCAL_IMAGE" > /dev/null 2>&1; then
    echo "Missing local image ${LOCAL_IMAGE} — run scripts/docker_build.sh first." >&2
    exit 1
  fi
done

for DIVISION in "${DIVISIONS[@]}"; do
  REPO_URL=$(terraform -chdir=infra output -json ecr_repository_urls | python3 -c "import json,sys; print(json.load(sys.stdin)['$DIVISION'])")
  LOCAL_IMAGE="${ECR_REGISTRY_PLACEHOLDER}/${DIVISION}:${IMAGE_TAG}"
  REMOTE_IMAGE="${REPO_URL}:${IMAGE_TAG}"

  docker tag "$LOCAL_IMAGE" "$REMOTE_IMAGE"

  aws ecr get-login-password --region "$REGION" | \
    docker login --username AWS --password-stdin "$REPO_URL"

  echo "Pushing ${DIVISION} -> ${REMOTE_IMAGE}"
  docker push "$REMOTE_IMAGE"
  echo "Pushed ${REMOTE_IMAGE}"
done

echo ""
echo "All images pushed with tag: ${IMAGE_TAG}"
echo "Update terraform.tfvars: lambda_image_tag = { electronica = \"${IMAGE_TAG}\", supermercado = \"${IMAGE_TAG}\", moda = \"${IMAGE_TAG}\", marketplace = \"${IMAGE_TAG}\" }"
