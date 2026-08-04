import json

import pytest

pytestmark = pytest.mark.cloud

DIVISIONS = ["electronica", "supermercado", "moda", "marketplace"]


def test_aws_identity(aws_client):
    sts = aws_client("sts")
    identity = sts.get_caller_identity()
    assert identity["Account"], "Expected a non-empty AWS account ID"
    print(f"Connected as: {identity['Arn']}")


def test_data_bucket_accessible(aws_client, tf_outputs):
    bucket = tf_outputs["data_bucket_name"]["value"]
    s3 = aws_client("s3")
    s3.head_bucket(Bucket=bucket)
    print(f"Data bucket OK: {bucket}")


@pytest.mark.parametrize("division", DIVISIONS)
def test_ingestion_lambda_exists(aws_client, tf_outputs, division):
    arn = tf_outputs["lambda_function_arns"]["value"][division]
    function_name = arn.split(":")[-1]
    lambda_client = aws_client("lambda")
    config = lambda_client.get_function(FunctionName=function_name)
    assert config["Configuration"]["State"] in ("Active", "Pending")
    print(f"Lambda OK ({division}): {arn}")


@pytest.mark.parametrize("division", DIVISIONS)
def test_ingestion_log_group_exists(aws_client, tf_outputs, division):
    log_group = tf_outputs["lambda_log_group_names"]["value"][division]
    logs = aws_client("logs")
    groups = logs.describe_log_groups(logGroupNamePrefix=log_group)
    assert groups["logGroups"], f"Log group not found: {log_group}"
    print(f"CloudWatch log group OK ({division}): {log_group}")


def test_glue_database_exists(aws_client, tf_outputs):
    database_name = tf_outputs["glue_database_name"]["value"]
    glue = aws_client("glue")
    result = glue.get_database(Name=database_name)
    assert result["Database"]["Name"] == database_name
    print(f"Glue database OK: {database_name}")


def test_glue_crawler_exists(aws_client, tf_outputs):
    crawler_name = tf_outputs["glue_crawler_name"]["value"]
    glue = aws_client("glue")
    result = glue.get_crawler(Name=crawler_name)
    assert result["Crawler"]["Name"] == crawler_name
    print(f"Glue crawler OK: {crawler_name}")


def test_athena_workgroup_exists(aws_client, tf_outputs):
    workgroup_name = tf_outputs["athena_workgroup_name"]["value"]
    athena = aws_client("athena")
    result = athena.get_work_group(WorkGroup=workgroup_name)
    assert result["WorkGroup"]["Name"] == workgroup_name
    print(f"Athena workgroup OK: {workgroup_name}")


def test_bucket_eventbridge_notifications_enabled(aws_client, tf_outputs):
    bucket = tf_outputs["data_bucket_name"]["value"]
    s3 = aws_client("s3")
    config = s3.get_bucket_notification_configuration(Bucket=bucket)
    assert config.get("EventBridgeConfiguration") is not None, (
        f"EventBridge notifications not enabled on bucket {bucket}"
    )
    print(f"EventBridge notifications enabled on bucket: {bucket}")


@pytest.mark.parametrize("division", DIVISIONS)
def test_ingestion_eventbridge_rule_exists_and_enabled(aws_client, tf_outputs, division):
    rule_name = tf_outputs["eventbridge_rule_names"]["value"][division]
    events = aws_client("events")
    rule = events.describe_rule(Name=rule_name)
    assert rule["State"] == "ENABLED", f"Rule {rule_name} is not ENABLED"
    print(f"EventBridge rule OK ({division}, ingestion): {rule_name}")


@pytest.mark.parametrize("division", DIVISIONS)
def test_transform_eventbridge_rule_exists_and_enabled(aws_client, tf_outputs, division):
    rule_name = tf_outputs["eventbridge_transform_rule_names"]["value"][division]
    events = aws_client("events")
    rule = events.describe_rule(Name=rule_name)
    assert rule["State"] == "ENABLED", f"Rule {rule_name} is not ENABLED"
    print(f"EventBridge rule OK ({division}, transform): {rule_name}")


@pytest.mark.parametrize("division", DIVISIONS)
def test_ingestion_eventbridge_rule_targets_correct_lambda(aws_client, tf_outputs, division):
    rule_name = tf_outputs["eventbridge_rule_names"]["value"][division]
    expected_arn = tf_outputs["lambda_function_arns"]["value"][division]
    events = aws_client("events")
    targets = events.list_targets_by_rule(Rule=rule_name)["Targets"]
    assert len(targets) == 1, f"Expected exactly 1 target for {rule_name}, got {len(targets)}"
    assert targets[0]["Arn"] == expected_arn
    print(f"EventBridge target OK ({division}, ingestion): {rule_name} -> {expected_arn}")


@pytest.mark.parametrize("division", DIVISIONS)
def test_ingestion_lambda_has_eventbridge_invoke_permission(aws_client, tf_outputs, division):
    arn = tf_outputs["lambda_function_arns"]["value"][division]
    function_name = arn.split(":")[-1]
    rule_name = tf_outputs["eventbridge_rule_names"]["value"][division]

    events = aws_client("events")
    rule_arn = events.describe_rule(Name=rule_name)["Arn"]

    lambda_client = aws_client("lambda")
    policy = json.loads(lambda_client.get_policy(FunctionName=function_name)["Policy"])
    matching = [
        s
        for s in policy["Statement"]
        if s.get("Principal", {}).get("Service") == "events.amazonaws.com"
        and s.get("Condition", {}).get("ArnLike", {}).get("AWS:SourceArn") == rule_arn
    ]
    assert matching, (
        f"No events.amazonaws.com invoke permission scoped to rule {rule_arn} "
        f"found on {function_name}"
    )
    print(f"Lambda resource policy OK ({division}, ingestion): EventBridge invoke permission present")


def test_budget_exists(aws_client, tf_outputs):
    sts = aws_client("sts")
    account_id = sts.get_caller_identity()["Account"]
    budgets = aws_client("budgets")
    result = budgets.describe_budgets(AccountId=account_id)
    assert result["Budgets"], "No AWS Budgets found — deploy infra first"
    print(f"Budgets: {[b['BudgetName'] for b in result['Budgets']]}")
