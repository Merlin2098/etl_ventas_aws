# AWS Smoke Tests

Validates that the retail data lake infrastructure deployed by Terraform
(SPEC-004) is accessible and correctly configured.

## Requirements

- Python dependencies: `pip install -r requirements.txt -r requirements-dev.txt`
- AWS credentials in `infra/env/.env.credentials` (or as env vars)
- Infrastructure deployed: `terraform -chdir=infra apply`

## Run

```
python scripts/testing/run_cloud_tests.py
```

Tests skip automatically if credentials are not available.

## What is validated

| Test                              | Resource         | Validates                              |
|------------------------------------|-------------------|-----------------------------------------|
| `test_aws_identity`                | STS               | credentials + connectivity              |
| `test_data_bucket_accessible`      | S3                | data lake bucket exists + accessible    |
| `test_ingestion_lambda_exists`     | Lambda (x5)       | each division's function is Active      |
| `test_ingestion_log_group_exists`  | CloudWatch Logs   | each division's log group exists        |
| `test_glue_database_exists`        | Glue              | catalog database exists                 |
| `test_glue_crawler_exists`         | Glue              | Gold crawler exists                     |
| `test_athena_workgroup_exists`     | Athena            | workgroup exists                        |
| `test_budget_exists`               | Budgets           | at least one budget configured          |
