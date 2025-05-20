# Developer Guide: Jirassic Pack 🦖

---

## Table of Contents
- [Overview](#overview)
- [Codebase Structure](#codebase-structure)
- [Key Patterns & Conventions](#key-patterns--conventions)
- [Adding a New Feature](#adding-a-new-feature)
- [Output & Logging](#output--logging)
- [Error Handling & Troubleshooting](#error-handling--troubleshooting)
- [Testing](#testing)
- [Versioning & Release](#versioning--release)
- [Glossary](#glossary)
- [Contributing](#contributing)

---

## Overview

This guide covers advanced usage, extension, and contribution patterns for the Jirassic Pack CLI. It is intended for developers and contributors.

---

## Codebase Structure

- `jirassicpack/`
  - `cli.py` — Main CLI entrypoint, argument parsing, config loading, feature dispatch
  - `config.py` — Loads YAML, .env, and environment variables; handles option precedence
  - `jira_client.py` — Handles all Jira API interactions with retry/timeout logic
  - `utils.py` — Utilities for option access, validation, error handling, Markdown rendering, and prompt choices
  - `features/` — One module per feature (e.g., `create_issue.py`, `bulk_operations.py`)
  - `metrics.py`, `summary.py` — Additional reporting features
- `tests/` — (If present) Unit and integration tests
- `README.md` — User documentation
- `DEVELOPER_GUIDE.md` — This file

---

## Key Patterns & Conventions

- **Unified Markdown Output:** All features that generate reports must use the `render_markdown_report` utility for `.md` files. This ensures a consistent, accessible, and branded output.
- **JSON Output:** Where appropriate, features should also output `.json` files for raw data (see Create/Update/Bulk features).
- **Context-Rich Logging:** All info and error messages should include context (feature, user, batch, suffix) for traceability.
- **Prompting & Validation:** Use `get_option`, `validate_required`, and `validate_date` for all user input. Use `prompt_with_validation` for custom validation.
- **Retry/Skip Logic:** Wrap all network/file operations in `retry_or_skip` to allow users to retry or skip on failure.
- **Batch Mode:** Use `unique_suffix` in all output filenames to avoid overwriting files in batch runs.

> **Jira Note:**
> **JQL** – Jira Query Language, used to filter issues.

---

## Adding a New Feature

1. **Create a new module** in `jirassicpack/features/` (e.g., `my_feature.py`).
2. **Define a main function** (e.g., `def my_feature(jira, params, user_email=None, batch_index=None, unique_suffix=None):`).
3. **Prompt for options** using `get_option` from `utils.py`.
4. **Validate required fields** with `validate_required` and `validate_date`.
5. **Use `ensure_output_dir`** before writing any files.
6. **Use `unique_suffix`** in output filenames for batch safety.
7. **Wrap all file/network operations** in try/except and use the `error` utility for reporting.
8. **Register the feature** in `cli.py`'s `register_features()` and ensure it is mapped in `run_feature()`.
9. **Use the Markdown template** for all `.md` outputs. Add `.json` output if appropriate.
10. **Update the README and this guide** with new config/.env options and usage.

> **Jira Term:**
> **Issue** – A single work item in Jira (e.g., bug, task, story).

---

## Output & Logging

- **Markdown:** Use `render_markdown_report` for all `.md` outputs. Do not write Markdown directly.
- **JSON:** Use a helper (e.g., `write_create_issue_json`) for `.json` outputs. Include all relevant fields.
- **Output Directory:** Use `output_dir` from options/config. Always call `ensure_output_dir`.
- **unique_suffix:** Always append to output filenames in batch mode.
- **Logging:**
  - Use the provided logger (`info`, `error`) for all user-facing and error output.
  - All logs include context: feature, user, batch, suffix.
  - Log format is JSON by default; can be switched to plain text for debugging.
  - Sensitive data (API tokens, passwords) are always redacted.
  - Example log entry:
    ```json
    {"asctime": "2024-06-10 12:34:56,123", "levelname": "ERROR", "name": "jirassicpack", "message": "Failed to fetch issues: 401 Unauthorized", "feature": "bulk_operations", "user": "alice@example.com", "batch": 0, "suffix": "_1718038490_0"}
    ```

---

## Error Handling & Troubleshooting

- **Error Handling:**
  - Always validate required parameters at the start of each feature. Use `validate_required` and `validate_date`.
  - Use `try/except` blocks around all network and file operations. Log errors with `error()` and include full context (feature, user, batch, suffix).
  - Use `retry_or_skip` for all network/file operations to allow user to retry or skip on failure.
  - For batch mode, ensure each feature's errors are reported in the batch summary.
  - Example:
    ```python
    try:
        issues = jira.search_issues(...)
    except Exception as e:
        error(f"Failed to fetch issues: {e}", extra=context)
        return
    ```
- **Testing Error Cases:**
  - Test missing required options, invalid dates, and network failures.
  - Ensure errors are logged and surfaced to the user as described above.

> **Jira Term:**
> **Worklog** – A record of time spent on an issue.

---

## Testing

- Place tests in the `tests/` directory (if present).
- Use `pytest` or standard `unittest`.
- Test both happy paths and error cases (e.g., missing required options, invalid dates).
- Mock network calls to Jira for unit tests.
- Test Markdown and JSON output for structure and content.

---

## Versioning & Release

- **Versioning:**
  - Follows [Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH
  - Update the version in the CLI and documentation for each release.
- **Release Process:**
  1. Ensure all features and documentation are up to date.
  2. Run all tests (unit, integration, output validation).
  3. Bump the version number.
  4. Tag the release in git and push to GitHub.
  5. Update the changelog (if present).
  6. Announce the release and update the README/DEVELOPER_GUIDE as needed.

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

## Contributing

- Fork the repo and create a feature branch.
- Write clear, descriptive commit messages.
- Add or update tests as needed.
- Open a pull request with a summary of your changes.
- Be responsive to code review feedback.
- Update documentation for any new features or config options.

---

Happy hacking! 🦖 

---

## 🛡️ Error Handling & Logging (Advanced)

- **Error Handling:**
  - Always validate required parameters at the start of each feature. Use `validate_required` and `validate_date`.
  - Use `try/except` blocks around all network and file operations. Log errors with `error()` and include full context (feature, user, batch, suffix).
  - Use `retry_or_skip` for all network/file operations to allow user to retry or skip on failure.
  - For batch mode, ensure each feature's errors are reported in the batch summary.
  - Example:
    ```python
    try:
        issues = jira.search_issues(...)
    except Exception as e:
        error(f"Failed to fetch issues: {e}", extra=context)
        return
    ```

- **Logging:**
  - Use the provided logger (`info`, `error`) for all user-facing and error output.
  - All logs include context: feature, user, batch, suffix.
  - Log format is JSON by default; can be switched to plain text for debugging.
  - Sensitive data (API tokens, passwords) are always redacted.
  - Example log entry:
    ```json
    {"asctime": "2024-06-10 12:34:56,123", "levelname": "ERROR", "name": "jirassicpack", "message": "Failed to fetch issues: 401 Unauthorized", "feature": "bulk_operations", "user": "alice@example.com", "batch": 0, "suffix": "_1718038490_0"}
    ```

---

## 📝 Output & Testing

- **Markdown Output:**
  - Use `render_markdown_report` for all `.md` outputs. Do not write Markdown directly.
  - Include summary and details sections, and always use the unified template.
- **JSON Output:**
  - For create/update/bulk, use a helper to write `.json` output with all relevant fields.
- **Testing Output:**
  - Test both Markdown and JSON outputs for structure and content.
  - Use sample configs and check that output files are named correctly and contain expected data.
- **Testing Error Cases:**
  - Test missing required options, invalid dates, and network failures.
  - Ensure errors are logged and surfaced to the user as described above.

---

## 🏷️ Versioning & Release Process

- **Versioning:**
  - Follows [Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH
  - Update the version in the CLI and documentation for each release.
- **Release Process:**
  1. Ensure all features and documentation are up to date.
  2. Run all tests (unit, integration, output validation).
  3. Bump the version number.
  4. Tag the release in git and push to GitHub.
  5. Update the changelog (if present).
  6. Announce the release and update the README/DEVELOPER_GUIDE as needed.

---

## 🧑‍💻 Example: Adding a Feature with Robust Error Handling & Logging

```python
def my_feature(jira, options, user_email=None, batch_index=None, unique_suffix=None):
    context = build_context("my_feature", user_email, batch_index, unique_suffix)
    # Validate required params
    user = options.get('user')
    if not validate_required(user, 'user'):
        error("'user' is required.", extra=context)
        return
    # Validate date
    start_date = options.get('start_date')
    if not validate_date(start_date, 'start_date'):
        error("'start_date' is invalid.", extra=context)
        return
    # Main operation with retry/skip
    try:
        with retry_or_skip("Fetching data from Jira", context=context):
            data = jira.get_data(user, start_date)
    except Exception as e:
        error(f"Failed to fetch data: {e}", extra=context)
        return
    # Write output
    try:
        filename = f"output/my_feature_{user}_{start_date}{unique_suffix}.md"
        content = render_markdown_report(
            feature="my_feature",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="My Feature",
            summary_section="...",
            main_content_section="..."
        )
        with open(filename, 'w') as f:
            f.write(content)
        info(f"My feature report written to {filename}", extra=context)
    except Exception as e:
        error(f"Failed to write report: {e}", extra=context)
```

---

## 🧪 Example: Testing Error Cases

- **Missing Required Option:**
  - Config: `{}`
  - Expected: Error log and user message: `[ERROR] [my_feature] 'user' is required.`
- **Invalid Date:**
  - Config: `{user: 'alice', start_date: '2024-13-01'}`
  - Expected: Error log and user message: `[ERROR] [my_feature] 'start_date' is invalid.`
- **Network Failure:**
  - Simulate by disconnecting network or mocking API error.
  - Expected: Error log with traceback, user prompted to retry or skip.

## Logging, Error Handling, and Configuration Standards

### Feature Entrypoints
- All feature entrypoints must use the `@feature_error_handler('feature_name')` decorator.
- Do not use redundant try/except blocks for error handling in the main entrypoint; the decorator will handle errors and logging.

### Logging
- Use `contextual_log` for all structured logs, including feature, user, batch, and suffix context.
- Use the `info()` and `error()` utilities from `jirassicpack.utils.message_utils`, which automatically log to both the console and the structured log.
- Avoid direct use of `print()` for logging; use the provided logging utilities.

### Configuration
- All features must use the options dictionary (from `ConfigLoader().get_options(feature_name)`) for configuration.
- Do not access environment variables or config files directly in feature modules.

### Utilities
- Utility functions should use `contextual_log` for any logging.
- Follow the same logging and error handling patterns as features where applicable.

---

## Prompting and Validation Best Practices

### Using `prompt_with_schema`
All new feature prompt functions should use the shared `prompt_with_schema` utility for Marshmallow schema-based prompting and validation. This ensures a consistent, user-friendly, and maintainable approach across the codebase.

#### Example
```python
from jirassicpack.utils.validation_utils import prompt_with_schema
from marshmallow import Schema, fields

class MyFeatureOptionsSchema(Schema):
    user = fields.Str(required=True)
    start_date = fields.Str(required=True)
    end_date = fields.Str(required=True)
    # ... other fields ...

def prompt_my_feature_options(opts, jira=None):
    schema = MyFeatureOptionsSchema()
    return prompt_with_schema(schema, dict(opts), jira=jira)
```

#### Checklist for New Feature Prompts
- [ ] Define a Marshmallow schema for all required/optional options.
- [ ] Use `prompt_with_schema` in your prompt function.
- [ ] Pass the schema, initial options dict, and `jira` client if needed.
- [ ] Remove any manual validation loops or error handling (handled by the utility).
- [ ] Add/adjust docstrings and type hints for clarity.

#### Best Practices
- Use descriptive error messages in your schema (`error_messages={...}`) for a better user experience.
- For custom field prompts (choices, password, etc.), pass a `field_prompt_map` to `prompt_with_schema`.
- Use the `jira` argument for user/team selection fields.
- Keep prompt functions concise—let the utility handle the loop and error display.

See existing features for more examples.

---

## Centralized User-Facing Messages

All user-facing messages and error strings should use the constants defined in `jirassicpack.utils.messages`. This ensures consistency and makes localization easier.

### Example Usage
```python
from jirassicpack.utils.messages import SEE_NOBODY_CARES, FILE_WRITE_ERROR

info(SEE_NOBODY_CARES)
error(FILE_WRITE_ERROR.format(error=e))
```

### Best Practices
- Always use a constant from `messages.py` for any user-facing string.
- If a new message is needed, add it to `messages.py` with a descriptive name.
- Use `.format()` for messages with dynamic content.
- This approach makes it easy to update, localize, or audit all user-facing output.

--- 