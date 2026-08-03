# NOTE: Lambda requires CMD in exec (JSON array) form, which Docker does NOT
# variable-substitute at build time (unlike ENV/COPY/LABEL). ${DIVISION} in the
# CMD line below is therefore a literal placeholder, substituted by
# scripts/docker_push.sh via `sed` into a per-build temp Dockerfile before
# `docker build` runs — never left unresolved in the built image.
FROM public.ecr.aws/lambda/python:3.12
ARG DIVISION
ENV DIVISION=${DIVISION}
COPY src/lambda_ingestion/requirements-lambda.txt .
RUN pip install -r requirements-lambda.txt --no-cache-dir
COPY src/lambda_ingestion/common/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/common/
COPY src/lambda_ingestion/transform/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/transform/
COPY src/lambda_ingestion/__init__.py ${LAMBDA_TASK_ROOT}/lambda_ingestion/__init__.py
COPY src/lambda_ingestion/${DIVISION}/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/${DIVISION}/
COPY src/__init__.py ${LAMBDA_TASK_ROOT}/src/__init__.py
# Default CMD is the ingestion handler; Terraform overrides this via
# image_config.command for the transform Lambda of this same division, which
# reuses this image without a separate build (see SPEC-005).
CMD ["lambda_ingestion.__DIVISION__.handler.handler"]
