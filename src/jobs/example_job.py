from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class JobConfig:
    job_name: str
    source_uri: str
    target_dataset: str
    transformation_sql: str
    contract_path: str


def _read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def load_config(config_path: str = "src/config/job_config.yaml") -> JobConfig:
    config_data = yaml.safe_load(_read_text(config_path))
    return JobConfig(**config_data)


def build_job_plan(config: JobConfig) -> dict[str, object]:
    sql_text = _read_text(config.transformation_sql).strip()
    contract = json.loads(_read_text(config.contract_path))
    return {
        "job_name": config.job_name,
        "source_uri": config.source_uri,
        "target_dataset": config.target_dataset,
        "transformation_sql": sql_text,
        "contract": contract,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the example job configuration.")
    parser.add_argument("--config", default="src/config/job_config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    payload = {
        "config": asdict(config),
        "plan": build_job_plan(config),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
