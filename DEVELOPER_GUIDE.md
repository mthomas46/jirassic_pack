# Developer Guide: Jirassic Pack 🦖

## Overview

This guide covers advanced usage, extension, and contribution patterns for the Jirassic Pack CLI. It is intended for developers and contributors.

---

## Advanced UX Patterns

- **Section Headers:** Use `print_section_header("Feature Name")` at the start of each feature for a consistent, branded look. This prints ASCII art and alt text for screen readers.
- **Emojis/Icons:** Use relevant emojis in prompts and menus to match the CLI's theme and improve clarity.
- **Prompt Validation:** Use `prompt_with_validation(prompt, validate_func, error_msg)` for all required user input. This ensures inline error messages and a consistent experience.
- **Contextual Help:** Use `prompt_with_help(prompt, help_text)` to provide `[?]` help at any prompt.
- **Retry/Skip Logic:** Wrap all network operations in `retry_or_skip(action_desc, func, *args, **kwargs)` to allow users to retry or skip on failure.
- **Batch Summary:** For batch operations, print a summary table with error details for failed items.
- **Celebratory Output:** Use `celebrate_success()` after successful operations.
- **Accessibility:** All output after the banner should be screen reader friendly. Use alt text for ASCII art, and avoid excessive symbols.

---

## Writing Accessible CLI Features

- Limit ASCII art to the banner and section headers. Always provide alt text.
- Use clear, structured text for all progress and results.
- Ensure all prompts and summaries are accessible to screen readers.
- Test with a screen reader if possible.

---

## Writing and Running Tests

- Abstract prompt logic for easier mocking in tests.
- Write unit tests for prompt/validation logic and file output.
- Use sample config and output files in `/examples` for integration tests.
- Test error handling and retry/skip logic.

---

## Code Review Checklist

- [ ] All user-facing output uses `info()` or UX utilities (no direct `print()`)
- [ ] No unused imports or dead code
- [ ] All prompts use `prompt_with_validation` or `prompt_with_help`
- [ ] All network operations use `retry_or_skip`
- [ ] Batch operations print a summary table with error details
- [ ] All output is accessible and screen reader friendly
- [ ] Functions have docstrings and are well-commented

---

## Advanced Usage & Extension Patterns

- **Adding a New Feature:**
  1. Create a new file in `jirassicpack/features/`.
  2. Use the UX patterns above for prompts, validation, and output.
  3. Register the feature in `cli.py`.
- **Extending Prompts:**
  - Use `questionary's advanced features for auto-complete or dropdowns if needed.
- **Custom Output:**
  - Use Markdown for all output files. Include clear headers and summaries.
- **Accessibility:**
  - Always provide alt text for ASCII art and ensure all output is readable by screen readers.

---

## Reference

See the updated `README.md` for:
- Features overview
- Getting started
- Accessibility and troubleshooting
- Contributing guidelines

---

Happy hacking! ��

# Developer Guide: jirassicPack

This guide is for developers who want to contribute to or extend jirassicPack. It covers codebase structure, conventions, feature development, testing, and best practices.

## Codebase Structure

- `jirassicpack/`
  - `cli.py` — Main CLI entrypoint, argument parsing, config loading, feature dispatch
  - `config.py` — Loads YAML, .env, and environment variables; handles option precedence
  - `jira_client.py` — Handles all Jira API interactions with retry/timeout logic
  - `utils.py` — Utilities for option access, validation, error handling, and prompt choices
  - `features/` — One module per feature (e.g., `create_issue.py`, `bulk_operations.py`)
  - `metrics.py`, `summary.py` — Additional reporting features
- `tests/` — (If present) Unit and integration tests
- `README.md` — User documentation
- `DEVELOPER_GUIDE.md` — This file

## Adding a New Feature
1. **Create a new module** in `jirassicpack/features/` (e.g., `my_feature.py`).
2. **Define a main function** (e.g., `def my_feature(jira, options):`).
3. **Prompt for options** using `get_option` from `utils.py`.
4. **Validate required fields** with `validate_required` and `validate_date`.
5. **Use `ensure_output_dir`** before writing any files.
6. **Use `unique_suffix`** in output filenames for batch safety (see below).
7. **Wrap all file/network operations** in try/except and use the `error` utility for reporting.
8. **Register the feature** in `cli.py`'s `register_features()` and ensure it is mapped in `run_feature()`.
9. **Update the README and this guide** with new config/.env options and usage.

## Feature Registration & Option Precedence
- Register your feature in `register_features()` in `cli.py`.
- In batch mode, global options from the config are merged with per-feature options, with per-feature taking precedence.
- Option precedence: per-feature options > global options > environment variables > defaults.
- All features should accept and use the `unique_suffix` option for output files (see below).

## Batch Mode & unique_suffix
- In batch mode, each feature run gets a unique output file suffix (e.g., `_1681234567_0`).
- Use this suffix in all output filenames to avoid overwriting files from different runs.
- Example: `output/advanced_metrics_alice_2024-01-01_to_2024-01-31_1681234567_0.md`

## Code Style & Documentation
- Use snake_case for all variable, function, and config keys.
- Add a file-level comment explaining the feature/module.
- Add docstrings to all functions, describing parameters, return values, and logic.
- Use type annotations for all function signatures.
- Use early returns for error cases.
- Use the `error` utility for all error reporting.
- Keep prompting, validation, business logic, and output writing in separate functions where possible.
- **Review and update documentation**: If you add or change a feature, update both the README and this guide.

## Testing
- Place tests in the `tests/` directory (if present).
- Use `pytest` or standard `unittest`.
- Test both happy paths and error cases (e.g., missing required options, invalid dates).
- Mock network calls to Jira for unit tests.

## Error Handling & Validation
- Always validate required fields before making API calls or writing files.
- All date fields should be validated to be in `YYYY-MM-DD` format.
- All file and network operations should be wrapped in try/except blocks. Use the `error` utility for consistent error reporting.
- Output directories should be created automatically if they do not exist.
- Never print sensitive data (like API tokens) to the console or logs.

## Debugging & Tips
- Use print statements or logging for debugging, but remove or minimize them in production code.
- If a feature isn't running as expected, check the config keys and required options.
- Use the `unique_suffix` for all batch output files to avoid overwriting.
- If you add a new config or .env key, document it in both the README and the feature's docstring.
- For features that use JQL, be explicit about the key (e.g., `integration_jql` vs `jql`).

## Best Practices for New Contributors
- Read through the README and this guide before making changes.
- Follow the code style and documentation conventions.
- Test your changes locally before opening a pull request.
- If you add a new feature or config option, update the documentation.
- Ask questions or open an issue if you are unsure about anything.

## Contributing
- Fork the repo and create a feature branch.
- Write clear, descriptive commit messages.
- Add or update tests as needed.
- Open a pull request with a summary of your changes.
- Be responsive to code review feedback.

## Advanced Developer Usage Examples

### Writing a Feature That Uses Both Global and Per-Feature Options
When running in batch mode, global options are merged with per-feature options. In your feature, always use the merged `options` dict:
```python
def my_feature(jira, options):
    # This will get the per-feature value if present, else global, else env/default
    project = options.get('project')
    summary = options.get('summary')
    ...
```

### Handling unique_suffix for Parallel/Batch Runs
Always use the `unique_suffix` from options in your output filenames:
```python
def my_feature(jira, options):
    output_dir = options.get('output_dir', 'output')
    unique_suffix = options.get('unique_suffix', '')
    filename = f"{output_dir}/my_feature_output{unique_suffix}.md"
    ...
```
This ensures that batch and parallel runs do not overwrite each other's output.

### Custom Error Handling and Validation in a New Feature
Use the `validate_required` and `validate_date` utilities, and wrap all I/O in try/except:
```python
def my_feature(jira, options):
    user = options.get('user')
    if not validate_required(user, 'user'):
        return
    start_date = options.get('start_date')
    if not validate_date(start_date, 'start_date'):
        return
    try:
        issues = jira.search_issues(...)
    except Exception as e:
        error(f"Failed to fetch issues: {e}")
        return
    ...
```

### Registering a New Feature and Mapping Menu Keys
In `cli.py`, add your feature to `register_features()` and map it in `run_feature()`:
```python
# In register_features():
from jirassicpack.features import my_feature
FEATURE_REGISTRY['my_feature'] = my_feature.my_feature

# In run_feature():
menu_to_key = {
    ...
    "My Custom Feature": "my_feature",
}
```

### Writing Tests for a Feature with Mocked Jira API
Use `pytest` and mock the Jira client:
```python
def test_my_feature(tmp_path, mocker):
    mock_jira = mocker.Mock()
    mock_jira.search_issues.return_value = [{"key": "DEMO-1", "fields": {"summary": "Test"}}]
    options = {"user": "alice", "output_dir": str(tmp_path), "unique_suffix": "_test"}
    from jirassicpack.features import my_feature
    my_feature.my_feature(mock_jira, options)
    output_file = tmp_path / "my_feature_output_test.md"
    assert output_file.exists()
    assert "DEMO-1" in output_file.read_text()
```

### Advanced Patterns and Tips
- If your feature needs to prompt for choices, use the `choices` argument in `get_option`.
- For features that need to support both interactive and batch mode, always check for required options and prompt only if missing.
- Document any non-standard option keys (like `integration_jql`) in both the README and your feature's docstring.
- If your feature writes multiple output files, use both `output_dir` and `unique_suffix` for all of them.
- For features that need to run in parallel, avoid using any global state or static filenames.

---

For questions or help, open an issue or contact the maintainers. 