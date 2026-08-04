#!/usr/bin/env bash
set -euo pipefail

# Builds the 4 division Lambda images from the single docker/Dockerfile
# (SPEC-005 / SPEC-004 "Flujo de despliegue"). Local build only — no AWS
# credentials required, nothing is pushed. Run scripts/docker_push.sh
# afterwards to publish these images to ECR.
#
# Each image serves both Lambda functions of its division (ingestion +
# transform, SPEC-004/SPEC-005) — the transform function overrides the
# entrypoint via Terraform's image_config.command, no separate build needed.

DIVISIONS=(electronica supermercado moda marketplace)
IMAGE_TAG=$(git rev-parse --short HEAD)
ECR_REGISTRY_PLACEHOLDER="local-build"

TMP_DOCKERFILE=$(mktemp)
trap 'rm -f "$TMP_DOCKERFILE"' EXIT

for DIVISION in "${DIVISIONS[@]}"; do
  # CMD in Lambda images must use exec form, which Docker does not
  # variable-substitute at build time — resolve the __DIVISION__ placeholder
  # here before building (see docker/Dockerfile header comment).
  sed "s/__DIVISION__/${DIVISION}/g" docker/Dockerfile > "$TMP_DOCKERFILE"

  IMAGE_NAME="${ECR_REGISTRY_PLACEHOLDER}/${DIVISION}:${IMAGE_TAG}"
  echo "Building ${DIVISION} -> ${IMAGE_NAME}"
  docker build \
    --platform linux/amd64 \
    --provenance=false \
    --build-arg DIVISION="${DIVISION}" \
    --file "$TMP_DOCKERFILE" \
    -t "${IMAGE_NAME}" \
    .
  echo "Built ${IMAGE_NAME}"
done

echo ""
echo "All images built locally with tag: ${IMAGE_TAG}"
echo "Run scripts/docker_push.sh to publish them to ECR."
