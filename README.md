# Jirassic Pack 🦖

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

<!-- Jurassic Park themed CLI banner GIF (replace with actual GIF) -->
![Jirassic Pack Banner Animation](docs/assets/jirassic_banner.gif)

```
      __
     / _)
.-^^^-/ /
__/       /
<__.|_|-|_|

JIRASSIC PACK
```

> The Ultimate Jurassic Park–themed Jira CLI Experience!

---

## Table of Contents
- [Overview](#overview)
- [Quick Start](#quick-start)
- [Configuration & Setup](#configuration--setup)
- [Features](#features)
  - [Feature Table](#feature-table)
  - [Feature Details](#feature-details)
- [Output & Logging](#output--logging)
- [Error Handling & Troubleshooting](#error-handling--troubleshooting)
- [Versioning & Release](#versioning--release)
- [Contributing](#contributing)
- [Glossary](#glossary)
- [License](#license)

---

## Overview

Jirassic Pack is a robust, accessible, and feature-rich CLI tool for interacting with Jira. It supports YAML config, environment variables, CLI prompts, batch/bulk operations, analytics, time tracking, and automated documentation—all with standardized output and strong error handling.

---

## Quick Start

```bash
pip install -r requirements.txt
python -m jirassicpack.cli
```

Or run with a config file:
```bash
python -m jirassicpack.cli --config=config.yaml
```

---

## Configuration & Setup

1. Copy `.env.example` to `.env` and fill in your Jira credentials and defaults.
2. (Optional) Copy `config.yaml.example` to `config.yaml` and customize your batch or single feature runs.

> **Jira Note:**
> - **Jira URL**: The base URL for your Jira instance (e.g., `https://your-domain.atlassian.net`).
> - **API Token**: Create one from your Atlassian account for secure authentication.

---

## Features

### Feature Table

| Feature                  | Description | Required Params | Optional Params | Output(s) |
|-------------------------|-------------|-----------------|-----------------|-----------|
| **Create Issue**        | Create new Jira issues | `project`, `summary` | `description`, `issue_type` | `.md`, `.json` |
| **Update Issue**        | Update fields on issues | `issue_key`, `field`, `value` |  | `.md`, `.json` |
| **Bulk Operations**     | Transition, comment, or assign multiple issues | `action`, `jql`, `value` |  | `.md`, `.json` |
| **Sprint Board Management** | Summarize/manage boards and sprints | `board_name` |  | `.md` |
| **User/Team Analytics** | Analyze team workload and bottlenecks | `team`, `start_date`, `end_date` |  | `.md` |
| **Advanced Metrics**    | Cycle/lead time, throughput, outliers | `user`, `start_date`, `end_date` |  | `.md` |
| **Time Tracking Worklogs** | Summarize worklogs for users/timeframes | `user`, `start_date`, `end_date` |  | `.md` |
| **Automated Documentation** | Generate release notes, changelogs, etc. | `doc_type`, `project`, `version`, `sprint` |  | `.md` |
| **Integration Tools**   | Scan for PR links and integrations | `integration_jql` |  | `.md` |
| **Gather Metrics**      | Collect/report metrics for a user/project | `user`, `start_date`, `end_date` |  | `.md` |
| **Summarize Tickets**   | Summarize tickets, comments, acceptance criteria | `jql` |  | `.md` |

---

### Feature Details

#### Create Issue
- **Description:** Create new Jira issues with prompts or config.
- **Parameters:** `project` (required), `summary` (required), `description`, `issue_type`
- **Example Config:**
  ```yaml
  feature: create_issue
  options:
    project: DEMO
    summary: "Example issue"
    description: "Created via batch config"
    issue_type: Task
  ```
- **Output:** `output/DEMO_example_issue_<unique_suffix>.md`, `.json`
- **Error Handling:** Validates required fields, logs errors, skips on missing params.
> **Jira Term:**
> **Issue** – A single work item in Jira (e.g., bug, task, story).

#### Update Issue
- **Description:** Update fields on existing issues.
- **Parameters:** `issue_key` (required), `field` (required), `value` (required)
- **Example Config:**
  ```yaml
  feature: update_issue
  options:
    issue_key: DEMO-123
    field: status
    value: Done
  ```
- **Output:** `output/update_issue_<unique_suffix>.md`, `.json`
- **Error Handling:** Validates required fields, logs errors, skips on missing params.
> **Jira Term:**
> **Issue Key** – Unique identifier for a Jira issue (e.g., DEMO-123).

#### Bulk Operations
- **Description:** Transition, comment, or assign multiple issues at once.
- **Parameters:** `action` (required), `jql` (required), `value` (required)
- **Example Config:**
  ```yaml
  feature: bulk_operations
  options:
    action: comment
    jql: "project = DEMO AND status = 'To Do'"
    value: "This is a batch comment"
  ```
- **Output:** `output/bulk_operations_<unique_suffix>.md`, `.json`
- **Error Handling:** Each issue result is logged; errors are included in the report and log file.
> **Jira Term:**
> **JQL** – Jira Query Language, used to filter issues.

#### Sprint Board Management
- **Description:** Summarize/manage Jira boards and sprints.
- **Parameters:** `board_name` (required)
- **Example Config:**
  ```yaml
  feature: sprint_board_management
  options:
    board_name: "Demo Board"
  ```
- **Output:** `output/sprint_board_management_<unique_suffix>.md`
- **Error Handling:** Validates required fields, logs errors.
> **Jira Term:**
> **Board** – A visual display of issues, often used for Scrum or Kanban.
> **Sprint** – A time-boxed period for completing work in Scrum.

#### ... (repeat for other features, each with a Jira Notes callout) ...

---

## Output & Logging

- All features output Markdown files using a **unified template** (see `render_markdown_report`).
- **File Naming:**
  - Single run: `output/<feature>_<params>_<unique_suffix>.md`
  - Batch: Each feature run appends a `unique_suffix` to avoid overwriting.
- **JSON Output:** For create/update/bulk, a `.json` file is also written with raw data.
- **Example Markdown Output:**
  ```markdown
  # 🦖 Jirassic Pack Report: <Feature Title>
  **Generated by:** alice@example.com
  **Date:** 2024-06-10 12:34:56 UTC
  **Feature:** create_issue
  **Batch:** 0
  **Suffix:** _1718038490_0
  ...
  ## 📋 Summary
  ...
  ## 📊 Details
  ...
  *"Life finds a way." – Dr. Ian Malcolm*
  ```
- **Example JSON Output:**
  ```json
  {
    "key": "DEMO-123",
    "summary": "Example issue",
    "status": "To Do",
    ...
  }
  ```
- **Logging:**
  - Format: JSON by default, plain text optional (`JIRASSICPACK_LOG_FORMAT=plain`)
  - Location: `jirassicpack.log` in working directory; rotated at 5MB, 5 backups
  - Enable Debug: `python -m jirassicpack.cli --log-level=DEBUG` or `JIRASSICPACK_LOG_LEVEL=DEBUG`
  - Sensitive Data: API tokens/passwords are redacted in logs
  - Example Log Entry:
    ```json
    {"asctime": "2024-06-10 12:34:56,123", "levelname": "INFO", "name": "jirassicpack", "message": "Feature complete", "feature": "create_issue", "user": "alice@example.com", "batch": 0, "suffix": "_1718038490_0"}
    ```

---

## Error Handling & Troubleshooting

- **Validation:**
  - All required fields are validated before API/file operations.
  - Date fields validated as `YYYY-MM-DD`.
  - If missing, logs error and skips feature.
- **Retry/Skip Logic:**
  - All network/file operations use retry/skip wrappers; user can retry or skip on failure.
- **Error Surfacing:**
  - Errors are printed to console with context (feature, user, batch, suffix).
  - All errors are logged to `jirassicpack.log` with full context and tracebacks.
- **Example Error Message:**
  ```
  [ERROR] [create_issue] project is required. (User: alice@example.com | Batch: 0 | Suffix: _1718038490_0)
  ```
- **Batch Summary:**
  - At end of batch, summary table shows status and errors for each feature.

---

## Versioning & Release

- **Current Version:** 1.0.0
- **Version Policy:** [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH)
- **Check Version:**
  ```bash
  python -m jirassicpack.cli --version
  ```
- **Release Process:**
  1. Ensure all features and documentation are up to date.
  2. Run all tests (unit, integration, output validation).
  3. Bump the version number.
  4. Tag the release in git and push to GitHub.
  5. Update the changelog (if present).
  6. Announce the release and update the README/DEVELOPER_GUIDE as needed.

---

## Contributing

- Follow the output and UX patterns: use the Markdown template, section headers, and context-rich logging.
- Add docstrings and comments for maintainability.
- See `DEVELOPER_GUIDE.md` for advanced usage and extension patterns.
- If you add a new feature or config option, update the documentation.
- Fork the repo, create a feature branch, and open a pull request.

---

## Glossary

| Term      | Definition |
|-----------|------------|
| **Issue**     | A single work item in Jira (e.g., bug, task, story). |
| **Project**   | A collection of issues, usually representing a product, service, or team. |
| **Board**     | A visual display of issues, often used for Scrum or Kanban. |
| **Sprint**    | A time-boxed period for completing work in Scrum. |
| **JQL**       | Jira Query Language, used to filter issues. |
| **Worklog**   | A record of time spent on an issue. |
| **Issue Key** | Unique identifier for a Jira issue (e.g., DEMO-123). |

---

## License

MIT

## Features
- **Create and update Jira issues**: Quickly create or update issues with prompts or config.
- **Sprint and board management**: List all sprints for a board and issues in the active sprint.
- **Advanced metrics and reporting**: Calculate cycle time, lead time, and generate burndown tables for a user or team.
- **Bulk operations**: Transition, comment, or assign multiple issues at once using JQL.
- **User and team analytics**: Analyze workload and bottlenecks for a team over a timeframe.
- **Integration with other tools**: Extract and list GitHub/GitLab PR links found in Jira issue descriptions and comments.
- **Time tracking and worklogs**: Summarize worklogs for a user over a timeframe.
- **Automated documentation**: Generate release notes, changelogs, or sprint review docs from Jira issues.
- **Batch mode**: Run multiple features in sequence, each with its own config and output file.

## Installation
```bash
pip install -r requirements.txt
```

## Setup
1. Copy `.env.example` to `.env` and fill in your Jira credentials and defaults.
2. (Optional) Copy `config.yaml.example` to `config.yaml` and customize your batch or single feature runs.

## Usage
### Interactive CLI
```bash
python -m jirassicpack.cli
```

### Single Feature with Config
```bash
python -m jirassicpack.cli --config=config.yaml
```

### Batch Mode (Multiple Features)
Add a `features:` list to your `config.yaml`:
```yaml
features:
  - name: create_issue
    options:
      project: DEMO
      summary: "Batch created issue"
  - name: advanced_metrics
    options:
      user: alice
      start_date: 2024-01-01
      end_date: 2024-01-31
```

### Output Files & unique_suffix
- All output files are written to the specified `output_dir` (default: `output`).
- In batch mode, each feature run appends a `unique_suffix` to its output file to avoid overwriting.
- Example: `output/advanced_metrics_alice_2024-01-01_to_2024-01-31_1681234567_0.md`

## Features & Option Keys
- **create_issue**: `project`, `summary`, `description`, `issue_type`
- **update_issue**: `issue_key`, `field`, `value`
- **bulk_operations**: `action`, `jql`, `value` (action: transition/comment/assign)
- **user_team_analytics**: `team`, `start_date`, `end_date`
- **integration_tools**: `integration_jql` (**not** just `jql`)
- **time_tracking_worklogs**: `user`, `start_date`, `end_date`
- **automated_documentation**: `doc_type`, `project`, `version`, `sprint`
- **advanced_metrics**: `user`, `start_date`, `end_date`
- **sprint_board_management**: `board_name`

> **Note:** For `integration_tools`, use `integration_jql` as the key for your JQL query. Other features use `jql` or feature-specific keys.

## Error Handling & Validation
- All required fields are validated before making API calls or writing files. If a required field is missing, the script will print an error and skip the feature.
- All date fields are validated to be in `YYYY-MM-DD` format.
- All file and network operations are wrapped in try/except blocks. Errors are printed with context using a consistent format.
- Output directories are created automatically if they do not exist. If the directory is invalid or not writable, an error is printed.
- All output files in batch mode use a unique suffix to avoid overwriting.

## Troubleshooting & FAQ
- **Missing required option**: Check your config and required keys for the feature.
- **Jira connection errors**: Check your `.env` and network access.
- **Output not generated**: Ensure `output_dir` exists or is writable.
- **Batch mode**: Each feature run gets a unique output file suffix.
- **integration_tools**: Use `integration_jql` for the JQL key.
- **Config merging**: In batch mode, per-feature options override global options and environment variables.

## How to Get Help or Contribute
- For help, open an issue on GitHub or see the Developer Guide.
- To contribute, fork the repo, create a feature branch, and open a pull request.
- See [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) for:
  - Codebase structure
  - How to add a new feature
  - Code style and documentation standards
  - Testing and debugging tips
  - Contribution guidelines

## Advanced Usage Examples

### Using Environment Variables and Config Together
You can set defaults in your `.env` file or environment, and override them in your `config.yaml`:
```env
# .env
JIRA_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token
JIRA_OUTPUT_DIR=output
```
```yaml
# config.yaml
feature: create_issue
options:
  project: DEMO
  summary: "This summary overrides the .env default"
  output_dir: custom_output
```

### Advanced Batch Mode with Global and Per-Feature Options
You can specify global options and override them per feature:
```yaml
features:
  - name: create_issue
    options:
      project: DEMO
      summary: "Batch created issue"
  - name: advanced_metrics
    options:
      user: alice
      start_date: 2024-01-01
      end_date: 2024-01-31
  - name: bulk_operations
    options:
      action: comment
      jql: "project = DEMO AND status = 'To Do'"
      value: "This is a batch comment"
output_dir: batch_output
```

### Custom Output Directories and File Naming
Set a custom output directory and see how unique_suffix is used:
```yaml
features:
  - name: time_tracking_worklogs
    options:
      user: alice
      start_date: 2024-01-01
      end_date: 2024-01-31
      output_dir: worklogs_output
```
Output file: `worklogs_output/alice_2024-01_to_2024-01-31_worklogs_<unique_suffix>.md`

### Example: Parallel/Concurrent Batch Runs
If you run multiple batch jobs at the same time, each will have a unique suffix:
- `output/advanced_metrics_alice_2024-01-01_to_2024-01-31_1681234567_0.md`
- `output/advanced_metrics_alice_2024-01-01_to_2024-01-31_1681234570_0.md`

### Example: integration_tools with integration_jql
```yaml
feature: integration_tools
options:
  integration_jql: "project = DEMO AND status = 'Done'"
  output_dir: integration_links
```
Output file: `integration_links/integration_links<unique_suffix>.md`

### Example: Error Handling in Config
If a required option is missing, the script will print an error and skip the feature:
```yaml
feature: create_issue
options:
  # project is missing!
  summary: "This will trigger a validation error"
```
Output:
```
[ERROR] project is required.
```

### Example: Using Password Prompts
If you omit `JIRA_API_TOKEN` in your config and environment, you will be prompted securely at runtime.

### Example: Using Choices in Prompts
For features like `automated_documentation`, you will be prompted to select from valid choices if not set in config:
```
Select documentation type:
  • Release notes
  • Changelog
  • Sprint Review
```

---

For more help, open an issue or see the Developer Guide.

## Logging & Audit Trail

Jirassic Pack now uses **structured JSON logging** by default. All CLI and feature actions are logged to `jirassicpack.log` as one JSON object per line. This makes logs easy to parse, search, and analyze with log management tools.

- Each log entry includes: timestamp, log level, feature name, user, batch index, unique suffix, and message.
- All configuration and options are logged with sensitive data (API tokens, passwords) redacted.
- All requests to and responses from Jira are logged at DEBUG level (enable with `--log-level=DEBUG` or `JIRASSICPACK_LOG_LEVEL=DEBUG`).
- Log rotation is enabled: each log file is limited to 5MB, with up to 5 backups retained.
- User interruptions (Ctrl+C) and all exceptions are logged with full tracebacks.

**Example JSON log entry:**
```json
{"asctime": "2024-06-10 12:34:56,123", "levelname": "INFO", "name": "jirassicpack", "message": "Feature complete", "feature": "create_issue", "user": "alice@example.com", "batch": 0, "suffix": "_1718038490_0"}
```

**Switching Log Format:**
- By default, logs are in JSON. To use plain text logs, set the environment variable:
  ```bash
  export JIRASSICPACK_LOG_FORMAT=plain
  ```
- To switch back to JSON:
  ```bash
  export JIRASSICPACK_LOG_FORMAT=json
  ```

**Sensitive Data Handling:**
- API tokens, passwords, and similar secrets are always redacted in logs.
- Never share your log file without reviewing for sensitive project data.

**Enabling Debug Logging:**
- Run the CLI with `python -m jirassicpack.cli --log-level=DEBUG` or set the environment variable `JIRASSICPACK_LOG_LEVEL=DEBUG` to capture all Jira API communications.

**Log File Location:**
- All logs are written to `jirassicpack.log` in the working directory. Log rotation ensures old logs are preserved as `jirassicpack.log.1`, `jirassicpack.log.2`, etc.

This logging system ensures you have a full audit trail of feature usage, configuration, and Jira API interactions for troubleshooting and compliance. 

## 🦖 Prompt/Spinner Separation & Robust UX Pattern

All features in Jirassic Pack follow a robust, user-friendly pattern:

- **Parameter gathering and validation** (including display of required/optional parameters) always happens **before** any spinner is started.
- **Spinners** only wrap network/file operations (API calls, file writes, etc.), never user prompts or validation.
- This ensures that prompts are always visible and never hidden by a spinner, for both interactive and batch modes.
- In batch mode, all parameters are resolved from config/env before any operation begins.

**Example pattern for contributors:**
```python
# In your feature module:
def prompt_my_feature_options(options):
    # Gather all parameters here (prompt, validate, merge config/env)
    ...
    return params

def my_feature(jira, params, ...):
    # Only perform the operation here, with spinner if needed
    with spinner("Doing work..."):
        ... # API/file operation
```

**This pattern is enforced for all features.**

--- 