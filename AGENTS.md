# AGENTS.md

## Purpose

This file defines the working contract for AI agents in the current project.
It is intentionally project-name agnostic so it remains valid when copied into
or used to bootstrap another repository.

Agents should first inspect the repository and its active capabilities before
assuming a language, cloud provider, framework, or infrastructure stack.
Typical supported work may include:

* Python data jobs and helpers
* SQL transformations
* Terraform infrastructure
* Application and frontend code
* Config-driven workflows
* Lightweight testing and packaging workflows

---

## Knowledge Sources

Use:

* `ai/skills/` for patterns and best practices
* `ai/skills.yaml` as the authoritative skills index
* `ai/domains/index.md` for domain-based navigation across all skill areas
* `ai/policies/global.md` for cross-domain policies (advisory and required)
* `ai/context.yaml` as the authoritative AI context-generation configuration
* `specs/template/` for inherited contracts when that directory is present
* `specs/project/` for project-authored specs when that directory is present

To map a task to the relevant skills, consult `ai/skills.yaml` (canonical slug
index) and `ai/domains/index.md` (domain grouping). There is no manual trigger
table in this file — those sources are the single source of truth.

These files are project guidance and configuration inputs.
They are not executable orchestration logic.

---

## Operating Behaviour

When assisting in a project that contains this guidance:

* Understand the objective and current repository shape before acting
* Search for existing implementations before proposing new files; prefer
  modifying or extending existing code over creating new files or parallel
  structures — only create new files when no equivalent exists or the user
  explicitly requests it
* Discover relevant skills automatically from `ai/skills/`; match tasks by
  consulting `ai/skills.yaml` and `ai/domains/index.md` without requiring
  explicit skill invocation by the user
* Apply patterns as guidance, not as rigid rules; enforce no rigid one-to-one
  mappings between tasks and skills
* Prefer simple, explicit changes over frameworks or abstractions
* Validate the result against repository principles and documented workflows

The agent must not:

* require explicit skill invocation
* create orchestration frameworks, skill composition systems, or meta-systems
* introduce hidden framework-like behavior

---

## Execution Rules

Use explicit project commands only.

Preferred workflow:

* run scripts directly with `python scripts/<script>.py`
* use Git Bash as the default terminal; use the documented wrapper flow under `scripts/python/`
* run Terraform commands directly and intentionally from `infra/`

Do not introduce hidden automation.

---

## Package Manager Awareness

Projects using this guidance use `pip` with `requirements.txt` for Python
dependency management.

Inspect `requirements.txt` and `requirements-dev.txt` to resolve active
dependencies. Use `python -m venv` to create the virtual environment and
`pip install -r requirements.txt` (add `-r requirements-dev.txt` for
development tooling).

---

## Approval Boundaries

### Never without approval

* `terraform apply`
* `terraform destroy`
* modify infrastructure state
* overwrite data or generated artifacts intentionally owned by users

### Ask before

* IAM changes
* Terraform module changes
* paid AWS services or production-grade infrastructure defaults
* data contract updates
* budget limit or alert email changes
* CloudWatch log group deletion or retention reduction

---

## Principles

* separation of concerns across infra, code, and config
* SQL separate from Python
* config-driven pipelines
* contracts-first validation
* prefer simple over complex
* keep workflows explicit and reproducible

---

## Governance

Mandatory AWS/Terraform operational guardrails (SPEC-009), the IAM cross-module
placement rule (Policy 010), and the simplicity ladder (Policy 008) live in
`ai/policies/global.md`. Apply them when the project profile enables the
corresponding capability.

---

## Philosophy

Simple. Explicit. Reproducible.

AI is a helper for the current project, not the system itself.
