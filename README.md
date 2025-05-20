# Jirassic Pack 🦖

> The modern, Jurassic Park–themed CLI for Jira analytics, reporting, and automation.

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

<!-- Jurassic Park themed CLI banner GIF (replace with actual GIF) -->
![Jirassic Pack Banner Animation](docs/assets/jirassic_banner.gif)
<!-- If you have a demo GIF, add it here. -->
<!-- ![Demo GIF](docs/assets/jirassic_demo.gif) -->

---

## Key Features
- 🦖 Themed, interactive CLI for Jira
- 📊 Advanced analytics and reporting
- 📝 Create, update, and bulk-edit issues
- 🗂️ LLM-powered ticket categorization and summaries
- 📄 Automated documentation and release notes
- 🔗 Integration with GitHub/GitLab PRs
- ⏱️ Time tracking and worklogs
- 🧑‍💻 Batch mode for multi-feature automation
- 🦾 Local LLM integration (Ollama/Code Llama)
- 🪵 Structured JSON logging and audit trail

---

[Developer Guide](DEVELOPER_GUIDE.md) • [Open an Issue](https://github.com/your-repo/issues) • [Contributing](#contributing)

---

## Table of Contents
- [Overview](#overview)
- [Who is this for?](#who-is-this-for)
- [Why Jirassic Pack?](#why-jirassic-pack)
- [Quick Start](#quick-start)
- [Configuration & Setup](#configuration--setup)
- [Menus & Navigation](#menus--navigation)
- [Features](#features)
  - [Feature Table](#feature-table)
  - [Feature Details](#feature-details)
- [Log Monitoring & Analytics](#log-monitoring--analytics)
- [Output & Logging](#output--logging)
- [Error Handling & Troubleshooting](#error-handling--troubleshooting)
- [Advanced Usage](#advanced-usage)
- [Glossary](#glossary)
- [FAQ](#faq)
- [Security](#security)
- [Changelog](#changelog)
- [Community & Contact](#community--contact)
- [License](#license)
- [Local LLM Integration: Using Jirassic Pack with Ollama7BPoc](#local-llm-integration-using-jirassic-pack-with-ollama7bpoc)

---

## Overview

Jirassic Pack is a robust, accessible, and feature-rich CLI tool for interacting with Jira. It supports YAML config, environment variables, CLI prompts, batch/bulk operations, analytics, time tracking, and automated documentation—all with standardized output and strong error handling.

---

## Who is this for?

> - **Engineers:** Automate Jira workflows, generate reports, and analyze tickets.
> - **Managers:** Get high-level summaries, team analytics, and actionable insights.
> - **Data/DevOps:** Integrate with CI/CD, export logs, and monitor activity.

---

## Why Jirassic Pack?

> - **Themed, modern CLI**: Enjoy a fun, Jurassic Park–inspired interface.
> - **LLM-powered analytics**: Use AI to categorize, summarize, and analyze tickets.
> - **Batch mode**: Run multiple features in sequence for automation.
> - **Extensible**: Add new features easily; all are auto-discovered in the menu.
> - **Robust error handling**: Every operation is validated and logged.
> - **Local LLM support**: Use your own models for privacy and speed.
> - **Beautiful output**: Markdown, JSON, and rich CLI panels.

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

## Menus & Navigation

Jirassic Pack provides a robust, interactive CLI with the following menu structure:

### Main CLI Menu
```
Jira Connection & Users
  ├─ 🧪 Test connection to Jira
  ├─ 👥 Output all users
  ├─ 🧑‍💻 Get user by accountId/email
  ├─ 🔍 Search users
  ├─ 🔎 Search users by displayname and email
  ├─ 🏷️ Get user property
  └─ 🙋 Get current user (myself)
Issues & Tasks
  ├─ 📝 Create a new issue
  ├─ ✏️ Update an existing issue
  ├─ 📋 Get task (issue)
  ├─ 🔁 Bulk operations
Boards & Sprints
  └─ 📋 Sprint and board management
Analytics & Reporting
  ├─ 📊 Advanced metrics and reporting
  ├─ 👤 User and team analytics
  ├─ ⏱️ Time tracking and worklogs
  ├─ 📈 Gather metrics for a user
  └─ 🗂️ Summarize tickets
Integrations & Docs
  ├─ 🔗 Integration with other tools
  └─ 📄 Automated documentation
Preferences
  └─ ⚙️ Get mypreferences
Exit
  └─ 🚪 Exit
```

### Log Monitoring & Analytics Menu
```
Log Monitoring & Search
  ├─ Filter by log level
  ├─ Filter by feature/module
  ├─ Filter by correlation ID
  ├─ Filter by time frame
  ├─ Show summary
  ├─ Export filtered logs
  ├─ Analytics & Reports
  │   ├─ Error rate over time (hour/day)
  │   ├─ Top features by error count
  │   ├─ Most frequent error messages
  │   ├─ Batch run success/failure
  │   ├─ Batch run time-to-completion
  │   ├─ Anomaly detection (error spikes, feature-based)
  │   ├─ User activity analytics
  │   └─ Export analytics as JSON/Markdown
  └─ Exit log monitoring
```

---

## Features

### Feature Table

| Feature                  | Description | Required Params | Optional Params | Output(s) | Underlying Jira API Calls |
|-------------------------|-------------|-----------------|-----------------|-----------|--------------------------|
| **Create Issue**        | Create new Jira issues | `project`, `summary` | `description`, `issue_type` | `.md`, `.json` | `POST /rest/api/3/issue` |
| **Update Issue**        | Update fields on issues | `issue_key`, `field`, `value` |  | `.md`, `.json` | `PUT /rest/api/3/issue/{issueIdOrKey}` |
| **Bulk Operations**     | Transition, comment, or assign multiple issues | `action`, `jql`, `value` |  | `.md`, `.json` | `POST /rest/api/3/issue/bulk`, `POST /rest/api/3/issue/{issueIdOrKey}/comment`, `POST /rest/api/3/issue/{issueIdOrKey}/transitions` |
| **User/Team Analytics** | Analyze user/team activity, ticket stats, and generate analytics reports | `team`, `start_date`, `end_date` |  | `.md` | `GET /rest/api/3/search`, `GET /rest/api/3/user` |
| **Integration Tools**   | Scan issues for GitHub/GitLab PR links and generate integration reports | `integration_jql` |  | `.md` | `GET /rest/api/3/search` |
| **Time Tracking Worklogs** | Summarize worklogs for a user and timeframe, with detailed Markdown output | `user`, `start_date`, `end_date` |  | `.md` | `GET /rest/api/3/issue/{issueIdOrKey}/worklog` |
| **Automated Documentation** | Generate release notes, changelogs, or sprint reviews from Jira issues | `doc_type`, `project`, `version`, `sprint` |  | `.md` | `GET /rest/api/3/search` |
| **Advanced Metrics**    | Generate advanced metrics, breakdowns, and top-N analytics for issues | `user`, `start_date`, `end_date` |  | `.md` | `GET /rest/api/3/search` |
| **Sprint Board Management** | Summarize the state of a Jira board, sprints, and issues in the active sprint | `board_name` |  | `.md` | `GET /rest/agile/1.0/board`, `GET /rest/agile/1.0/board/{boardId}/sprint`, `GET /rest/agile/1.0/sprint/{sprintId}/issue` |
| **Deep Ticket Summary** | Generate a full summary of a ticket, including changelog, comments, and all fields | `issue_key` | `output_dir`, `acceptance_criteria_field` | `.md` | `GET /rest/api/3/issue`, `GET /rest/api/3/issue/{issueIdOrKey}/changelog`, `GET /rest/api/3/issue/{issueIdOrKey}/comment` |
| **Gather Metrics**      | Gather and report metrics for Jira issues, including grouping by type and summary statistics | `user`, `start_date`, `end_date` |  | `.md` | `GET /rest/api/3/search` |
| **Summarize Tickets**   | Generate summary reports for Jira tickets, including grouping, top assignees, and action items | `jql` |  | `.md` | `GET /rest/api/3/search`, `GET /rest/api/3/issue/{issueIdOrKey}/comment` |

---

### Feature Details

#### Create Issue
**Description:**  Create a new Jira issue in a specified project.

**Jira API:**  [`POST /rest/api/3/issue`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-post)

**Parameters:**
| Name        | Type   | Required | Description                |
|-------------|--------|----------|----------------------------|
| project     | str    | Yes      | Project key (e.g., DEMO)   |
| summary     | str    | Yes      | Issue summary/title        |
| description | str    | No       | Issue description          |
| issue_type  | str    | No       | Type (e.g., Task, Bug)     |

**Example Config:**
```yaml
feature: create_issue
options:
  project: DEMO
  summary: "Example issue"
  description: "Created via batch config"
  issue_type: Task
```

**Output:**  Markdown and JSON files in `output/`

**Error Handling:**  Validates required fields, logs errors, skips on missing params.

> **Jira Note:**
> **Issue** – A single work item in Jira (e.g., bug, task, story).

#### Update Issue
**Description:**  Update fields on existing issues.

**Jira API:**  [`PUT /rest/api/3/issue/{issueIdOrKey}`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-put)

**Parameters:**
| Name      | Type   | Required | Description                |
|-----------|--------|----------|----------------------------|
| issue_key | str    | Yes      | Issue key (e.g., DEMO-123) |
| field     | str    | Yes      | Field to update (e.g., status) |
| value     | str    | Yes      | New value                  |

**Example Config:**
```yaml
feature: update_issue
options:
  issue_key: DEMO-123
  field: status
  value: Done
```

**Output:**  Markdown and JSON files in `output/`

**Error Handling:**  Validates required fields, logs errors, skips on missing params.

> **Jira Note:**
> **Issue Key** – Unique identifier for a Jira issue (e.g., DEMO-123).

#### Bulk Operations
**Description:**  Transition, comment, or assign multiple issues at once using JQL.

**Jira API:**
- [`POST /rest/api/3/issue/bulk`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-bulk-post)
- [`POST /rest/api/3/issue/{issueIdOrKey}/comment`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/#api-rest-api-3-issue-issueidorkey-comment-post)
- [`POST /rest/api/3/issue/{issueIdOrKey}/transitions`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-transitions-post)

**Parameters:**
| Name    | Type   | Required | Description                |
|---------|--------|----------|----------------------------|
| action  | str    | Yes      | Action to perform (e.g., comment, transition) |
| jql     | str    | Yes      | JQL query to select issues |
| value   | str    | Yes      | Value for the action (e.g., comment text) |

**Example Config:**
```yaml
feature: bulk_operations
options:
  action: comment
  jql: "project = DEMO AND status = 'To Do'"
  value: "This is a batch comment"
```

**Output:**  Markdown and JSON files in `output/`

**Error Handling:**  Each issue result is logged; errors are included in the report and log file.

> **Jira Note:**
> **JQL** – Jira Query Language, used to filter issues.

#### User/Team Analytics
**Description:**  Analyze user/team activity, ticket stats, and generate analytics reports.

**Jira API:**  [`GET /rest/api/3/search`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-get), [`GET /rest/api/3/user`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-users/#api-rest-api-3-user-get)

**Parameters:**
| Name       | Type   | Required | Description                |
|------------|--------|----------|----------------------------|
| team       | str    | Yes      | Team name or ID            |
| start_date | str    | Yes      | Start date (YYYY-MM-DD)    |
| end_date   | str    | Yes      | End date (YYYY-MM-DD)      |

**Example Config:**
```yaml
feature: user_team_analytics
options:
  team: "Backend Team"
  start_date: 2024-01-01
  end_date: 2024-01-31
```

**Output:**  Markdown file in `output/`

**Error Handling:**  Validates required fields, logs errors.

> **Jira Note:**
> **User** – A Jira user account. **Team** – A group of users, often mapped to a project or board.

#### Integration Tools
**Description:**  Scan issues for GitHub/GitLab PR links and generate integration reports.

**Jira API:**  [`GET /rest/api/3/search`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-get)

**Parameters:**
| Name            | Type   | Required | Description                |
|-----------------|--------|----------|----------------------------|
| integration_jql | str    | Yes      | JQL query for integration issues |

**Example Config:**
```yaml
feature: integration_tools
options:
  integration_jql: "project = DEMO AND status = 'Done'"
```

**Output:**  Markdown file in `output/`

**Error Handling:**  Validates required fields, logs errors.

> **Jira Note:**
> **Integration** – Links to PRs or external tools in Jira issues.

#### Time Tracking Worklogs
**Description:**  Summarize worklogs for a user and timeframe, with detailed Markdown output.

**Jira API:**  [`GET /rest/api/3/issue/{issueIdOrKey}/worklog`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-worklogs/#api-rest-api-3-issue-issueidorkey-worklog-get)

**Parameters:**
| Name       | Type   | Required | Description                |
|------------|--------|----------|----------------------------|
| user       | str    | Yes      | User account/email         |
| start_date | str    | Yes      | Start date (YYYY-MM-DD)    |
| end_date   | str    | Yes      | End date (YYYY-MM-DD)      |

**Example Config:**
```yaml
feature: time_tracking_worklogs
options:
  user: alice
  start_date: 2024-01-01
  end_date: 2024-01-31
```

**Output:**  Markdown file in `output/`

**Error Handling:**  Validates required fields, logs errors.

> **Jira Note:**
> **Worklog** – A record of time spent on an issue.

#### Automated Documentation
**Description:**  Generate release notes, changelogs, or sprint reviews from Jira issues.

**Jira API:**  [`GET /rest/api/3/search`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-get)

**Parameters:**
| Name      | Type   | Required | Description                |
|-----------|--------|----------|----------------------------|
| doc_type  | str    | Yes      | Type of doc (Release notes, Changelog, Sprint Review) |
| project   | str    | Yes      | Project key                |
| version   | str    | No       | Version name               |
| sprint    | str    | No       | Sprint name                |

**Example Config:**
```yaml
feature: automated_documentation
options:
  doc_type: Release notes
  project: DEMO
  version: 1.2.3
```

**Output:**  Markdown file in `output/`

**Error Handling:**  Validates required fields, logs errors.

> **Jira Note:**
> **Release Notes** – A summary of changes for a release. **Changelog** – A list of changes/issues for a version.

#### Advanced Metrics
**Description:**  Generate advanced metrics, breakdowns, and top-N analytics for issues.

**Jira API:**  [`GET /rest/api/3/search`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-get)

**Parameters:**
| Name       | Type   | Required | Description                |
|------------|--------|----------|----------------------------|
| user       | str    | Yes      | User account/email         |
| start_date | str    | Yes      | Start date (YYYY-MM-DD)    |
| end_date   | str    | Yes      | End date (YYYY-MM-DD)      |

**Example Config:**
```yaml
feature: advanced_metrics
options:
  user: alice
  start_date: 2024-01-01
  end_date: 2024-01-31
```

**Output:**  Markdown file in `output/`

**Error Handling:**  Validates required fields, logs errors.

> **Jira Note:**
> **Cycle Time** – Time from issue start to completion. **Lead Time** – Time from issue creation to completion.

#### Sprint Board Management
**Description:**  Summarize the state of a Jira board, sprints, and issues in the active sprint.

**Jira API:**
- [`GET /rest/agile/1.0/board`](https://developer.atlassian.com/cloud/jira/software/rest/api-group-boards/#api-rest-agile-1-0-board-get)
- [`GET /rest/agile/1.0/board/{boardId}/sprint`](https://developer.atlassian.com/cloud/jira/software/rest/api-group-sprints/#api-rest-agile-1-0-board-boardid-sprint-get)
- [`GET /rest/agile/1.0/sprint/{sprintId}/issue`](https://developer.atlassian.com/cloud/jira/software/rest/api-group-sprint-issues/#api-rest-agile-1-0-sprint-sprintid-issue-get)

**Parameters:**
| Name       | Type   | Required | Description                |
|------------|--------|----------|----------------------------|
| board_name | str    | Yes      | Name of the board          |

**Example Config:**
```yaml
feature: sprint_board_management
options:
  board_name: "Demo Board"
```

**Output:**  Markdown file in `output/`

**Error Handling:**  Validates required fields, logs errors.

> **Jira Note:**
> **Board** – A visual display of issues, often used for Scrum or Kanban.
> **Sprint** – A time-boxed period for completing work in Scrum.

#### Deep Ticket Summary
**Description:**  Generate a full summary of a ticket, including changelog, comments, and all fields.

**Jira API:**
- [`GET /rest/api/3/issue`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-get)
- [`GET /rest/api/3/issue/{issueIdOrKey}/changelog`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-changelog/#api-rest-api-3-issue-issueidorkey-changelog-get)
- [`GET /rest/api/3/issue/{issueIdOrKey}/comment`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/#api-rest-api-3-issue-issueidorkey-comment-get)

**Parameters:**
| Name                | Type   | Required | Description                |
|---------------------|--------|----------|----------------------------|
| issue_key           | str    | Yes      | Issue key                  |
| output_dir          | str    | No       | Output directory           |
| acceptance_criteria_field | str | No       | Acceptance criteria field |

**Example Config:**
```yaml
feature: deep_ticket_summary
options:
  issue_key: DEMO-123
  output_dir: summary_output
  acceptance_criteria_field: "Acceptance Criteria"
```

**Output:**  Markdown file in `output/`

**Error Handling:**  Validates required fields, logs errors.

> **Jira Note:**
> **Acceptance Criteria** – Conditions that must be met for a ticket to be considered complete.

#### Gather Metrics
**Description:**  Gather and report metrics for Jira issues, including grouping by type and summary statistics.

**Jira API:**  [`GET /rest/api/3/search`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-get)

**Parameters:**
| Name       | Type   | Required | Description                |
|------------|--------|----------|----------------------------|
| user       | str    | Yes      | User account/email         |
| start_date | str    | Yes      | Start date (YYYY-MM-DD)    |
| end_date   | str    | Yes      | End date (YYYY-MM-DD)      |

**Example Config:**
```yaml
feature: gather_metrics
options:
  user: alice
  start_date: 2024-01-01
  end_date: 2024-01-31
```

**Output:**  Markdown file in `output/`

**Error Handling:**  Validates required fields, logs errors.

#### Summarize Tickets
**Description:**  Generate summary reports for Jira tickets, including grouping, top assignees, and action items.

**Jira API:**
- [`GET /rest/api/3/search`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-get)
- [`GET /rest/api/3/issue/{issueIdOrKey}/comment`](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/#api-rest-api-3-issue-issueidorkey-comment-get)

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| jql  | str  | Yes      | JQL query   |

**Example Config:**
```yaml
feature: summarize_tickets
options:
  jql: "project = DEMO AND status = 'Done'"
```

**Output:**  Markdown file in `output/`

**Error Handling:**  Validates required fields, logs errors.

> **Jira Note:**
> **Acceptance Criteria** – Conditions that must be met for a ticket to be considered complete.

---

## Log Monitoring & Analytics

Jirassic Pack includes a powerful log monitoring and analytics CLI:

### How to Launch
- From the main CLI menu: **Log Monitoring & Search**
- Or directly: `python log_monitoring.py`

### Menu Options
- **Filter by log level**: Show only INFO, ERROR, etc.
- **Filter by feature/module**: Show logs for a specific feature.
- **Filter by correlation ID**: Trace a batch run or operation.
- **Filter by time frame**: Show logs within a date/time range.
- **Show summary**: Count of logs by level and feature.
- **Export filtered logs**: Save filtered logs as JSON.
- **Analytics & Reports**:
  - Error rate over time (hour/day)
  - Top features by error count
  - Most frequent error messages
  - Batch run success/failure
  - Batch run time-to-completion
  - Anomaly detection (error spikes, feature-based)
  - User activity analytics
  - Export analytics as JSON/Markdown
- **Exit log monitoring**: Return to CLI or exit.

### Analytics & Reports Details
- **Error rate over time:** Shows error counts per hour or day.
- **Top features by error count:** Lists features/modules with the most errors.
- **Most frequent error messages:** Aggregates and counts unique error messages.
- **Batch run success/failure:** Summarizes batch runs by correlation ID, showing counts and rates of success vs. failure, and durations.
- **Batch run time-to-completion:** Calculates and reports average, min, max duration for batch operations.
- **Anomaly detection:** Highlights time periods or features with error rates significantly above average (z-score or threshold).
- **User activity analytics:** Shows most active users, actions per user, and error rates per user.
- **Export analytics:** Save analytics as Markdown or JSON for sharing or documentation.

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

## Advanced Usage

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

## Local LLM Integration: Using Jirassic Pack with Ollama7BPoc

To enable local code analysis and technical summaries, Jirassic Pack can work in tandem with a local LLM server (such as Code Llama via Ollama7BPoc).

### How it Works
- The local LLM project (`../Ollama7BPoc`) exposes HTTP endpoints for text, file, and GitHub PR analysis.
- Jirassic Pack routes code/PR analysis and technical summary features to these endpoints when configured.
- All other summaries (e.g., general ticket summaries) use OpenAI by default.

### Running Both Projects Together

You can use the following script to start both the local LLM server and Jirassic Pack (run in separate terminals or as background processes):

```bash
# Start the Ollama LLM server (Terminal 1)
ollama serve &

# Start the local LLM HTTP API (Terminal 2)
cd ../Ollama7BPoc
pip install -r requirements.txt
python http_api.py &

# Start Jirassic Pack CLI (Terminal 3)
cd ../jirassicPack
pip install -r requirements.txt
python -m jirassicpack.cli
```

> **Note:** You can also create a shell script (e.g., `start_local_llm_and_jirassic.sh`) to automate these steps.

### Can This Be Run from the Main Menu?
Currently, starting the local LLM server (`ollama serve` and `python http_api.py`) must be done manually or via a shell script. However, adding a "Start Local LLM Server" option to the Jirassic Pack main menu is a possible future enhancement. This would allow you to launch the local LLM server directly from the CLI for even smoother integration.

### What Happens
- When you use features like code/PR analysis or technical summaries, Jirassic Pack sends requests to the local LLM API (e.g., `http://localhost:5000/generate/text`).
- The local LLM (Ollama7BPoc) processes the request and returns the result to Jirassic Pack.
- This allows you to use a local, private LLM for code analysis, while still using OpenAI for other summaries.

See the `jirassicpack/features/ticket_discussion_summary.py` and `jirassicpack/features/test_local_llm.py` for example usage and integration points.

--- 

## Requirements & Setup

### Dependencies

Install all required packages:

```sh
pip install -r requirements.txt
```

**Key dependencies:**
- `aiohttp>=3.9.0` (required for Python 3.12 compatibility)
- `questionary` – Interactive CLI prompts
- `rich` – Beautiful output, panels, and tracebacks
- `marshmallow` – Input/config validation
- `InquirerPy` – Fuzzy finder and advanced selection for large lists
- `psutil` – Process management for LLM server orchestration
- `python-dotenv` – Environment variable loading
- `pyfiglet`, `colorama`, `tqdm`, `yaspin` – Theming, banners, progress
- `requests`, `PyYAML`, `PyGithub`, `openai` – API and integration

### Python Version

Jirassic Pack is tested and supported on **Python 3.12**. Older versions (e.g., 3.8–3.11) may work, but Python 3.12 is recommended for best compatibility and support.

> **Note:** If you use Python 3.12, you must have `aiohttp>=3.9.0` (already specified in requirements.txt).

### Virtual Environment (Recommended)

Create and activate a Python 3.12 virtual environment:

```sh
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file or set these variables:

```
JIRA_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token
```

You will be prompted for any missing values on first run.

---

## Quickstart

Run the CLI:

```sh
python -m jirassicpack.cli
```

or

```sh
python jirassicpack/cli.py
```

---

## Advanced CLI UX

- **Fuzzy Finder:** For large lists (users, boards, sprints, etc.), type to search and filter instantly.
- **Pagination & Jump-to-Letter:** For medium lists, navigate with next/prev, jump to page, or jump to a letter.
- **Jurassic Park–Themed Panels:** Enjoy themed banners, panels, and Easter eggs throughout the CLI.
- **Beautiful Output:** All prompts, errors, and info use `rich` for a modern, readable experience.

---

## Local LLM Integration

- Start/stop the local LLM server from the main menu or via shell script.
- Test the local LLM endpoints directly from the CLI.

---

## Troubleshooting

- If you see missing package errors, run `pip install -r requirements.txt` again.
- For local LLM issues, check logs or use the "Test Local LLM" menu.

---

For more, see the full feature list and usage examples below! 

## FAQ

<details>
<summary>How do I reset my config?</summary>
Delete or edit your `.jirassicpack_cli_state.json` and `.env` files, or use the Settings menu in the CLI.
</details>

<details>
<summary>How do I add a new feature?</summary>
See the [Developer Guide](DEVELOPER_GUIDE.md#adding-a-new-feature). In short: create a new module in `jirassicpack/features/`, add it to `FEATURE_MANIFEST`, and it will appear in the menu.
</details>

<details>
<summary>How do I use the local LLM?</summary>
See the [Local LLM Integration](#local-llm-integration-using-jirassic-pack-with-ollama7bpoc) section. Start the local server, then use features that support LLM.
</details>

<details>
<summary>How do I get help or report a bug?</summary>
Open an issue on GitHub or see the [Contributing](#contributing) section.
</details>

---

## Security

> **Sensitive data (API tokens, passwords) are always redacted in logs.**
> - Never share your log file without reviewing for sensitive project data.
> - If you discover a security issue, please report it privately via GitHub issues or email the maintainer.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes and version history.

---

## Community & Contact

- For questions, open an issue or discussion on GitHub.
- To contribute, fork the repo and open a pull request.
- For real-time chat, join our (planned) Discord or Slack (link TBD).

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

--- 