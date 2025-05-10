# Changelog

## [Unreleased]
- Add auto-complete for project/user/board fields (planned)
- Add persistent user preferences (planned)

## [1.0.0] - 2024-05-09
### Added
- Jurassic Park–themed ASCII art banner and branding
- Section headers with ASCII art and alt text for screen readers
- Emojis/icons in all menus and prompts
- Inline validation and error messages for all user input
- Contextual help: `[?]` at any prompt for help
- Retry/skip logic for all network operations
- Batch summary tables with error details
- Celebratory output (confetti emoji) on success
- Screen reader friendly: all output after the banner is clear, with alt text for headers
- Consistent use of `info()` for all user-facing output
- Modular, maintainable code structure
- Comprehensive developer guide and code review checklist

### Changed
- Refactored all file writers to use `info()` instead of `print()`
- Removed redundant validation and unused imports
- Enhanced batch summary to include error messages for failed items

### Fixed
- No known outstanding bugs

---

See `README.md` and `DEVELOPER_GUIDE.md` for usage and contribution details. 