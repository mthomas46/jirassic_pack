"""
log_monitoring.py

Log parsing, analytics, and monitoring utilities for Jirassic Pack.
Provides interactive CLI for log search, filtering, correlation, anomaly detection, and reporting.
All analytics are modular, robust, and exportable as Markdown or JSON.
"""

# =========================
# Imports and Constants
# =========================
import json
import argparse
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import os
from collections import Counter, defaultdict
from tabulate import tabulate
from statistics import mean, stdev
from jirassicpack.utils.validation_utils import safe_get
from jirassicpack.utils.prompt_utils import prompt_text, prompt_select
from jirassicpack.utils.logging import contextual_log
from jirassicpack.analytics.helpers import build_report_sections

LOG_FILE = 'jirassicpack.log'
INTERVAL_CHOICES = ["hour", "day"]
LOG_LEVEL_CHOICES = ["INFO", "ERROR", "WARNING", "DEBUG"]

# =========================
# Core Log Parsing Utilities
# =========================
def parse_logs(log_file: str = LOG_FILE) -> List[Dict[str, Any]]:
    """
    Parse the log file and return a list of log entries (as dicts).
    Supports JSON log format (default for Jirassic Pack). Skips malformed lines.

    Args:
        log_file: Path to the log file.
    Returns:
        List of log entry dictionaries.
    """
    logs: List[Dict[str, Any]] = []
    if not os.path.exists(log_file):
        print(f"Log file not found: {log_file}")
        return logs
    with open(log_file, 'r') as file:
        for line in file:
            try:
                entry = json.loads(line)
                logs.append(entry)
            except Exception:
                continue  # Skip malformed lines
    return logs


def filter_logs(
    logs: List[Dict[str, Any]],
    level: Optional[str] = None,
    feature: Optional[str] = None,
    correlation_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Filter logs by level, feature, correlation ID, and time frame.

    Args:
        logs: List of log entry dictionaries.
        level: Log level to filter by (e.g., 'ERROR').
        feature: Feature/module name to filter by.
        correlation_id: Correlation ID to filter by.
        start_time: Start time (YYYY-MM-DD HH:MM:SS) for filtering.
        end_time: End time (YYYY-MM-DD HH:MM:SS) for filtering.
    Returns:
        Filtered list of log entries.
    """
    def parse_time(timestamp: str):
        try:
            return datetime.strptime(timestamp.split(',')[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    filtered_logs = logs
    if correlation_id:
        filtered_logs = [log for log in filtered_logs if log.get('correlation_id') == correlation_id]
    if level:
        filtered_logs = [log for log in filtered_logs if log.get('levelname', '').upper() == level.upper()]
    if feature:
        filtered_logs = [log for log in filtered_logs if log.get('feature') == feature]
    if start_time:
        start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        filtered_logs = [log for log in filtered_logs if parse_time(log.get('asctime', '')) and parse_time(log.get('asctime', '')) >= start_dt]
    if end_time:
        end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        filtered_logs = [log for log in filtered_logs if parse_time(log.get('asctime', '')) and parse_time(log.get('asctime', '')) <= end_dt]
    return filtered_logs


def error_rate_over_time(logs, interval='hour'):
    time_format = "%Y-%m-%d %H:%M:%S"
    buckets = defaultdict(int)
    for log in logs:
        if log.get('levelname', '').upper() == 'ERROR':
            asctime = log.get('asctime', '')
            try:
                dt = datetime.strptime(asctime.split(',')[0], time_format)
                if interval == 'hour':
                    bucket = dt.strftime('%Y-%m-%d %H:00')
                elif interval == 'day':
                    bucket = dt.strftime('%Y-%m-%d')
                else:
                    bucket = dt.strftime('%Y-%m-%d %H:%M:%S')
                buckets[bucket] += 1
            except Exception:
                continue
    return dict(sorted(buckets.items()))


def top_features_by_error(logs, top_n=5):
    feature_counter = Counter()
    for log in logs:
        if log.get('levelname', '').upper() == 'ERROR':
            feature = log.get('feature', 'N/A')
            feature_counter[feature] += 1
    return feature_counter.most_common(top_n)


def most_frequent_error_messages(logs, top_n=5):
    msg_counter = Counter()
    for log in logs:
        if log.get('levelname', '').upper() == 'ERROR':
            msg = log.get('message', 'N/A')
            msg_counter[msg] += 1
    return msg_counter.most_common(top_n)


def batch_run_success_failure(logs):
    # Group by correlation_id, count successes and failures
    batch_stats = defaultdict(lambda: {'success': 0, 'failure': 0, 'start': None, 'end': None})
    for log in logs:
        cid = log.get('correlation_id')
        if not cid:
            continue
        lvl = log.get('levelname', '').upper()
        asctime = log.get('asctime', '')
        if lvl == 'ERROR':
            batch_stats[cid]['failure'] += 1
        elif lvl == 'INFO':
            batch_stats[cid]['success'] += 1
        # Track start/end times
        try:
            dt = datetime.strptime(asctime.split(',')[0], "%Y-%m-%d %H:%M:%S")
            if not batch_stats[cid]['start'] or dt < batch_stats[cid]['start']:
                batch_stats[cid]['start'] = dt
            if not batch_stats[cid]['end'] or dt > batch_stats[cid]['end']:
                batch_stats[cid]['end'] = dt
        except Exception:
            pass
    # Prepare table
    table = []
    for correlation_id, batch_stat in batch_stats.items():
        duration = (batch_stat['end'] - batch_stat['start']).total_seconds() if batch_stat['start'] and batch_stat['end'] else None
        table.append([correlation_id, batch_stat['success'], batch_stat['failure'], duration])
    return table


def batch_run_time_analytics(logs):
    # For each correlation_id, compute duration
    times = defaultdict(lambda: {'start': None, 'end': None})
    for log in logs:
        cid = log.get('correlation_id')
        if not cid:
            continue
        asctime = log.get('asctime', '')
        try:
            dt = datetime.strptime(asctime.split(',')[0], "%Y-%m-%d %H:%M:%S")
            if not times[cid]['start'] or dt < times[cid]['start']:
                times[cid]['start'] = dt
            if not times[cid]['end'] or dt > times[cid]['end']:
                times[cid]['end'] = dt
        except Exception:
            pass
    durations = [(correlation_id, (time_info['end'] - time_info['start']).total_seconds() if time_info['start'] and time_info['end'] else None) for correlation_id, time_info in times.items()]
    if durations:
        avg = sum(duration for _, duration in durations if duration is not None) / max(1, len([duration for _, duration in durations if duration is not None]))
        min_d = min((duration for _, duration in durations if duration is not None), default=None)
        max_d = max((duration for _, duration in durations if duration is not None), default=None)
    else:
        avg = min_d = max_d = None
    return durations, avg, min_d, max_d


def export_markdown(headers: List[str], rows: List[Any], analytics_type: str, export_path: str, summary: Optional[str] = None) -> None:
    """
    Export analytics as a Markdown file, creating directories as needed.
    Adds summary if provided. Prints error if writing fails.

    Args:
        headers: List of column headers.
        rows: List of data rows.
        analytics_type: Description of the analytics/report.
        export_path: Path to write the Markdown file.
        summary: Optional summary string to append.
    Output:
        Writes a Markdown file with a table and optional summary.
    """
    table_md = render_table(rows, headers)
    sections = {
        'header': f"# 🦖 Analytics Report: {analytics_type}",
        'summary': summary or '',
        'grouped_sections': table_md,
    }
    markdown = build_report_sections(sections)
    try:
        dir_path = os.path.dirname(export_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
        with open(export_path, 'w') as file:
            file.write(markdown)
        print(f"Analytics report exported as Markdown to {export_path}")
    except Exception as error:
        print(f"Failed to write analytics report to {export_path}: {error}")


def anomaly_detection(logs, interval='hour', threshold=2.0):
    """
    Detect time periods or features with error rates significantly above average (z-score > threshold).
    Returns a list of (bucket, error_count, z_score).
    """
    # Time-based anomaly detection
    error_counts = error_rate_over_time(logs, interval=interval)
    values = list(error_counts.values())
    if len(values) < 2:
        return []
    avg = mean(values)
    std = stdev(values)
    anomalies = []
    for bucket, count in error_counts.items():
        z = (count - avg) / std if std > 0 else 0
        if z > threshold:
            anomalies.append((bucket, count, round(z, 2)))
    return anomalies


def user_activity_analytics(logs, top_n=5):
    """
    Show most active users, actions per user, and error rates per user.
    Returns a list of (user, total_actions, error_count, error_rate).
    """
    user_counter = Counter()
    error_counter = Counter()
    for log in logs:
        user = log.get('user', 'N/A')
        user_counter[user] += 1
        if log.get('levelname', '').upper() == 'ERROR':
            error_counter[user] += 1
    table = []
    for user, total in user_counter.most_common(top_n):
        errors = error_counter[user]
        error_rate = errors / total if total else 0
        table.append((user, total, errors, f"{error_rate:.2%}"))
    return table


def feature_anomaly_detection(logs, threshold=2.0):
    """
    Detect features/modules with error rates significantly above average (z-score > threshold).
    Returns a list of (feature, error_count, z_score).
    """
    # Count errors per feature
    feature_counts = Counter()
    for log in logs:
        if log.get('levelname', '').upper() == 'ERROR':
            feature = log.get('feature', 'N/A')
            feature_counts[feature] += 1
    values = list(feature_counts.values())
    if len(values) < 2:
        return []
    avg = mean(values)
    std = stdev(values)
    anomalies = []
    for feature, count in feature_counts.items():
        z = (count - avg) / std if std > 0 else 0
        if z > threshold:
            anomalies.append((feature, count, round(z, 2)))
    return anomalies


# =========================
# Analytics Registry and Helpers
# =========================
ANALYTICS_REGISTRY = {
    "Error rate over time": {
        "func": lambda logs, interval: list(error_rate_over_time(logs, interval=interval).items()),
        "headers": ["Time", "Error Count"],
        "prompts": [{"name": "Interval (hour/day)", "value": "select", "choices": INTERVAL_CHOICES, "default": "hour"}],
    },
    "Top features by error count": {
        "func": lambda logs, top_n: top_features_by_error(logs, top_n=top_n),
        "headers": ["Feature", "Error Count"],
        "prompts": [{"name": "Show top N features (integer)", "value": "int", "choices": None, "default": 5}],
    },
    "Most frequent error messages": {
        "func": lambda logs, top_n: most_frequent_error_messages(logs, top_n=top_n),
        "headers": ["Error Message", "Count"],
        "prompts": [{"name": "Show top N error messages (integer)", "value": "int", "choices": None, "default": 5}],
    },
    "Batch run success/failure": {
        "func": lambda logs: batch_run_success_failure(logs),
        "headers": ["Correlation ID", "Successes", "Failures", "Duration (s)"],
        "prompts": [],
    },
    "Batch run time-to-completion": {
        "func": lambda logs: batch_run_time_analytics(logs)[0],
        "headers": ["Correlation ID", "Duration (s)"],
        "prompts": [],
        "summary": lambda logs: batch_run_time_analytics(logs)[1:],
    },
    "Anomaly detection (error spikes)": {
        "func": lambda logs, interval, threshold: zscore_anomaly(error_rate_over_time(logs, interval=interval), threshold),
        "headers": ["Time", "Error Count", "Z-score"],
        "prompts": [{"name": "Interval (hour/day)", "value": "select", "choices": INTERVAL_CHOICES, "default": "hour"}, {"name": "Z-score threshold (float)", "value": "float", "choices": None, "default": 2.0}],
    },
    "Feature-based anomaly detection": {
        "func": lambda logs, threshold: zscore_anomaly(feature_error_counts(logs), threshold),
        "headers": ["Feature", "Error Count", "Z-score"],
        "prompts": [{"name": "Z-score threshold (float)", "value": "float", "choices": None, "default": 2.0}],
    },
    "User activity analytics": {
        "func": lambda logs, top_n: user_activity_analytics(logs, top_n=top_n),
        "headers": ["User", "Total Actions", "Error Count", "Error Rate"],
        "prompts": [{"name": "Show top N users (integer)", "value": "int", "choices": None, "default": 5}],
    },
}

def safe_prompt(label: str, typ: str, choices=None, default=None) -> Any:
    """
    Prompt the user for input, safely convert to the desired type, and re-prompt on error.
    Handles select, int, float, and text types.
    Args:
        label: Prompt label.
        typ: Type of input ('select', 'int', 'float', 'text').
        choices: List of choices for select prompts.
        default: Default value.
    Returns:
        User input, converted to the correct type.
    """
    while True:
        try:
            if typ == "select":
                return prompt_select(label + ":", choices=choices, default=default)
            elif typ == "int":
                value = prompt_text(label + ":", default=str(default))
                return int(value)
            elif typ == "float":
                value = prompt_text(label + ":", default=str(default))
                return float(value)
            else:
                return prompt_text(label + ":", default=str(default))
        except (ValueError, TypeError):
            print(f"Invalid input. Please enter a valid {typ}.")


def zscore_anomaly(counts: Dict[str, int], threshold: float) -> List[Tuple[str, int, float]]:
    """
    Compute z-score anomalies for a dict of counts. Return entries above threshold.

    Args:
        counts: Dictionary mapping keys (e.g., time buckets or features) to integer counts.
        threshold: Z-score threshold for anomaly detection.
    Returns:
        List of tuples: (key, count, z-score) for entries where z-score > threshold.
        Returns an empty list if fewer than 2 entries.
    Example:
        >>> zscore_anomaly({'A': 2, 'B': 10, 'C': 3}, 1.5)
        [('B', 10, 1.73)]
    """
    count_values = list(counts.values())
    if len(count_values) < 2:
        return []
    avg = mean(count_values)
    std = stdev(count_values)
    return [
        (key, count, round((count - avg) / std, 2))
        for key, count in counts.items()
        if std > 0 and (count - avg) / std > threshold
    ]


def feature_error_counts(logs: List[Dict[str, Any]]) -> Counter:
    """
    Count errors per feature/module in the logs.

    Args:
        logs: List of log entry dictionaries.
    Returns:
        Counter mapping feature name to error count.
    """
    feature_counts = Counter()
    for log_entry in logs:
        if safe_get(log_entry, ['levelname'], '').upper() == 'ERROR':
            feature = safe_get(log_entry, ['feature'], 'N/A')
            feature_counts[feature] += 1
    return feature_counts


def render_table(data: List[Any], headers: List[str]) -> str:
    """
    Render a table using tabulate, or a message if data is empty.

    Args:
        data: List of rows (each row is a list or tuple).
        headers: List of column headers.
    Returns:
        Markdown-formatted table as a string, or a message if data is empty.
    """
    if not data:
        return "No data available."
    return tabulate(data, headers=headers, tablefmt="github")


# =========================
# Analytics Menu (Interactive)
# =========================
def analytics_menu(logs: List[Dict[str, Any]]) -> None:
    """
    Interactive analytics/reporting menu. Handles prompts, runs analytics, and supports export.
    Uses the ANALYTICS_REGISTRY for modularity.

    Args:
        logs: List of log entry dictionaries.
    """
    analytics_last = None
    analytics_type_last = None
    analytics_headers_last = None
    analytics_summary_last = None
    while True:
        analytics_choices = list(ANALYTICS_REGISTRY.keys()) + [
            "Export last analytics report (JSON)",
            "Export last analytics report (Markdown)",
            "Back to main menu"
        ]
        analytics_action = prompt_select(
            "Select analytics/report:",
            choices=analytics_choices
        )
        if analytics_action in ANALYTICS_REGISTRY:
            entry = ANALYTICS_REGISTRY[analytics_action]
            params = []
            for prompt in entry.get("prompts", []):
                label, typ, choices, default = prompt['name'], prompt['value'], prompt.get('choices'), prompt.get('default')
                value = safe_prompt(label, typ, choices, default)
                params.append(value)
            result = entry["func"](logs, *params)
            analytics_last = result
            analytics_type_last = analytics_action
            analytics_headers_last = entry["headers"]
            analytics_summary_last = None
            if "summary" in entry:
                summary_vals = entry["summary"](logs)
                if summary_vals:
                    avg, min_duration, max_duration = summary_vals
                    analytics_summary_last = (
                        f"Average: {avg:.2f} s, Min: {min_duration:.2f} s, Max: {max_duration:.2f} s"
                        if avg is not None else "No durations available."
                    )
            print(f"\n{analytics_action}:")
            print(render_table(result, entry["headers"]))
            if analytics_summary_last:
                print(analytics_summary_last)
        elif analytics_action == "Export last analytics report (JSON)":
            if analytics_last is None:
                print("No analytics report to export yet.")
            else:
                export_path = prompt_text("Export analytics report to file:", default="analytics_report.json")
                try:
                    dir_path = os.path.dirname(export_path)
                    if dir_path and not os.path.exists(dir_path):
                        os.makedirs(dir_path)
                    with open(export_path, 'w') as file:
                        json.dump({
                            "type": analytics_type_last,
                            "data": analytics_last,
                            "headers": analytics_headers_last,
                            "summary": analytics_summary_last
                        }, file, indent=2)
                    print(f"Analytics report exported to {export_path}")
                except Exception as error:
                    print(f"Failed to write analytics report to {export_path}: {error}")
        elif analytics_action == "Export last analytics report (Markdown)":
            if analytics_last is None:
                print("No analytics report to export yet.")
            else:
                export_path = prompt_text("Export analytics report to file:", default="analytics_report.md")
                export_markdown(
                    analytics_headers_last,
                    analytics_last,
                    analytics_type_last,
                    export_path,
                    summary=analytics_summary_last
                )
        elif analytics_action == "Back to main menu":
            break

# =========================
# Main Interactive Log Monitoring Feature
# =========================
def log_parser(jira=None, options=None, user_email=None, batch_index=None, unique_suffix=None):
    contextual_log('info', f"log_parser called with jira={jira}, options={options}, user_email={user_email}, batch_index={batch_index}, unique_suffix={unique_suffix}", extra={"feature": "log_parser", "user": user_email, "batch": batch_index, "suffix": unique_suffix})
    print("\n🦖 Log Parser & Search \n")
    log_file = prompt_text("Path to log file:", default=LOG_FILE)
    logs = parse_logs(log_file)
    if not logs:
        print("No logs found.")
        return
    while True:
        action = prompt_select(
            "Select log filter/search option:",
            choices=[
                "Filter by log level",
                "Filter by feature/module",
                "Filter by correlation ID",
                "Filter by time frame",
                "Show summary",
                "Export filtered logs",
                "Exit log parser"
            ]
        )
        filtered_logs = logs
        if action == "Filter by log level":
            log_level = prompt_select("Select log level:", choices=LOG_LEVEL_CHOICES)
            filtered_logs = filter_logs(logs, level=log_level)
        elif action == "Filter by feature/module":
            feature_names = sorted(set(safe_get(log, ['feature'], 'N/A') for log in logs))
            selected_feature = prompt_select("Select feature:", choices=[{"name": feature, "value": feature} for feature in feature_names])
            filtered_logs = filter_logs(logs, feature=selected_feature["value"])
        elif action == "Filter by correlation ID":
            correlation_ids = sorted(set(safe_get(log, ['correlation_id'], 'N/A') for log in logs if safe_get(log, ['correlation_id'])))
            if not correlation_ids:
                print("No correlation IDs found in logs.")
                continue
            selected_correlation_id = prompt_select("Select correlation ID:", choices=[{"name": cid, "value": cid} for cid in correlation_ids])
            filtered_logs = filter_logs(logs, correlation_id=selected_correlation_id["value"])
        elif action == "Filter by time frame":
            start_time = prompt_text("Start time (YYYY-MM-DD HH:MM:SS):", default="")
            end_time = prompt_text("End time (YYYY-MM-DD HH:MM:SS):", default="")
            filtered_logs = filter_logs(logs, start_time=start_time or None, end_time=end_time or None)
        elif action == "Show summary":
            print(f"Total log entries: {len(logs)}")
            level_counts = {}
            feature_counts = {}
            for log_entry in logs:
                level = safe_get(log_entry, ['levelname'], 'N/A')
                feature = safe_get(log_entry, ['feature'], 'N/A')
                level_counts[level] = level_counts.get(level, 0) + 1
                feature_counts[feature] = feature_counts.get(feature, 0) + 1
            print("Log entries by level:")
            for level, count in level_counts.items():
                print(f"  {level}: {count}")
            print("Log entries by feature:")
            for feature, count in feature_counts.items():
                print(f"  {feature}: {count}")
            continue
        elif action == "Export filtered logs":
            export_path = prompt_text("Export filtered logs to file:", default="filtered_logs.json")
            try:
                dir_path = os.path.dirname(export_path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path)
                with open(export_path, 'w') as file:
                    json.dump(filtered_logs, file, indent=2)
                print(f"Filtered logs exported to {export_path}")
            except Exception as error:
                print(f"Failed to write filtered logs to {export_path}: {error}")
            continue
        elif action == "Exit log parser":
            print("Exiting log parser.")
            break
        # Show filtered logs (if not summary/export/exit)
        if action.startswith("Filter"):
            print(f"\nFiltered log entries: {len(filtered_logs)}\n")
            for log_entry in filtered_logs[:50]:  # Show up to 50 entries
                print(json.dumps(log_entry, indent=2))
            if len(filtered_logs) > 50:
                print(f"... {len(filtered_logs)-50} more entries not shown ...")

# =========================
# CLI Entrypoint for Standalone Use
# =========================
def main() -> None:
    """
    CLI entrypoint for log monitoring utility. Supports basic filtering via args.

    Args:
        --log-file: Path to the log file.
        --correlation-id: Filter logs by correlation ID.
        --level: Filter logs by log level.
    """
    parser = argparse.ArgumentParser(description="Jirassic Pack Log Monitoring Utility")
    parser.add_argument('--log-file', type=str, default=LOG_FILE, help='Path to the log file')
    parser.add_argument('--correlation-id', type=str, help='Filter logs by correlation ID')
    parser.add_argument('--level', type=str, help='Filter logs by level (INFO, ERROR, etc.)')
    args = parser.parse_args()

    logs = parse_logs(args.log_file)
    if args.correlation_id:
        logs = [log for log in logs if safe_get(log, ['correlation_id']) == args.correlation_id]
    if args.level:
        logs = [log for log in logs if safe_get(log, ['levelname'], '').upper() == args.level.upper()]

    for log_entry in logs:
        print(json.dumps(log_entry, indent=2))

    # TODO: Add monitoring/alerting logic (e.g., error rate, anomaly detection, etc.)

if __name__ == '__main__':
    main() 