"""
log_monitoring.py

Scaffold for log parsing and monitoring utilities for Jirassic Pack.
This module can be extended to provide log search, filtering, correlation, and alerting.
"""
import json
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime
import questionary
import os
from collections import Counter, defaultdict
from tabulate import tabulate
from statistics import mean, stdev

LOG_FILE = 'jirassicpack.log'


def parse_logs(log_file: str = LOG_FILE) -> List[Dict[str, Any]]:
    """
    Parse the log file and return a list of log entries (as dicts).
    Supports JSON log format (default for Jirassic Pack).
    """
    entries = []
    if not os.path.exists(log_file):
        print(f"Log file not found: {log_file}")
        return entries
    with open(log_file, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                entries.append(entry)
            except Exception:
                continue  # Skip malformed lines
    return entries


def filter_logs(logs: List[Dict[str, Any]], level: Optional[str] = None, feature: Optional[str] = None, correlation_id: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None) -> List[Dict[str, Any]]:
    def parse_time(ts):
        try:
            return datetime.strptime(ts.split(',')[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    filtered = logs
    if correlation_id:
        filtered = [log for log in filtered if log.get('correlation_id') == correlation_id]
    if level:
        filtered = [log for log in filtered if log.get('levelname', '').upper() == level.upper()]
    if feature:
        filtered = [log for log in filtered if log.get('feature') == feature]
    if start_time:
        start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        filtered = [log for log in filtered if parse_time(log.get('asctime', '')) and parse_time(log.get('asctime', '')) >= start_dt]
    if end_time:
        end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        filtered = [log for log in filtered if parse_time(log.get('asctime', '')) and parse_time(log.get('asctime', '')) <= end_dt]
    return filtered


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
    for cid, stats in batch_stats.items():
        duration = (stats['end'] - stats['start']).total_seconds() if stats['start'] and stats['end'] else None
        table.append([cid, stats['success'], stats['failure'], duration])
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
    durations = [(cid, (v['end'] - v['start']).total_seconds() if v['start'] and v['end'] else None) for cid, v in times.items()]
    if durations:
        avg = sum(d for _, d in durations if d is not None) / max(1, len([d for _, d in durations if d is not None]))
        min_d = min((d for _, d in durations if d is not None), default=None)
        max_d = max((d for _, d in durations if d is not None), default=None)
    else:
        avg = min_d = max_d = None
    return durations, avg, min_d, max_d


def export_markdown_analytics(analytics_type, analytics_data, export_path):
    md = f"# 🦖 Analytics Report: {analytics_type}\n\n"
    if isinstance(analytics_data, dict):
        md += tabulate(analytics_data.items(), headers=["Key", "Value"], tablefmt="github")
    elif isinstance(analytics_data, list):
        if analytics_type.startswith("Batch run"):
            md += tabulate(analytics_data, headers=["Correlation ID", "Successes", "Failures", "Duration (s)"] if analytics_type.startswith("Batch run success/failure") else ["Correlation ID", "Duration (s)"], tablefmt="github")
        elif analytics_type.startswith("Top") or analytics_type.startswith("Most"):
            md += tabulate(analytics_data, headers=["Value", "Count"], tablefmt="github")
        else:
            md += tabulate(analytics_data, tablefmt="github")
    else:
        md += str(analytics_data)
    with open(export_path, 'w') as f:
        f.write(md)
    print(f"Analytics report exported as Markdown to {export_path}")


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


# --- Analytics Registry and Helpers ---
ANALYTICS_REGISTRY = {
    "Error rate over time": {
        "func": lambda logs, interval: list(error_rate_over_time(logs, interval=interval).items()),
        "headers": ["Time", "Error Count"],
        "prompts": [("Interval", "select", ["hour", "day"], "hour")],
    },
    "Top features by error count": {
        "func": lambda logs, top_n: top_features_by_error(logs, top_n=top_n),
        "headers": ["Feature", "Error Count"],
        "prompts": [("Show top N features", "int", None, 5)],
    },
    "Most frequent error messages": {
        "func": lambda logs, top_n: most_frequent_error_messages(logs, top_n=top_n),
        "headers": ["Error Message", "Count"],
        "prompts": [("Show top N error messages", "int", None, 5)],
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
        "prompts": [("Interval", "select", ["hour", "day"], "hour"), ("Z-score threshold", "float", None, 2.0)],
    },
    "Feature-based anomaly detection": {
        "func": lambda logs, threshold: zscore_anomaly(feature_error_counts(logs), threshold),
        "headers": ["Feature", "Error Count", "Z-score"],
        "prompts": [("Z-score threshold", "float", None, 2.0)],
    },
    "User activity analytics": {
        "func": lambda logs, top_n: user_activity_analytics(logs, top_n=top_n),
        "headers": ["User", "Total Actions", "Error Count", "Error Rate"],
        "prompts": [("Show top N users", "int", None, 5)],
    },
}

def zscore_anomaly(counts: dict, threshold: float):
    values = list(counts.values())
    if len(values) < 2:
        return []
    avg, std = mean(values), stdev(values)
    return [(k, v, round((v-avg)/std, 2)) for k, v in counts.items() if std > 0 and (v-avg)/std > threshold]

def feature_error_counts(logs):
    feature_counts = Counter()
    for log in logs:
        if log.get('levelname', '').upper() == 'ERROR':
            feature = log.get('feature', 'N/A')
            feature_counts[feature] += 1
    return feature_counts

def render_table(data, headers):
    if not data:
        return "No data available."
    return tabulate(data, headers=headers, tablefmt="github")

def export_markdown(headers, rows, analytics_type, export_path, summary=None):
    md = f"# 🦖 Analytics Report: {analytics_type}\n\n"
    md += render_table(rows, headers)
    if summary:
        md += f"\n\n{summary}"
    with open(export_path, 'w') as f:
        f.write(md)
    print(f"Analytics report exported as Markdown to {export_path}")

def analytics_menu(logs):
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
        analytics_action = questionary.select(
            "Select analytics/report:",
            choices=analytics_choices
        ).ask()
        if analytics_action in ANALYTICS_REGISTRY:
            entry = ANALYTICS_REGISTRY[analytics_action]
            params = []
            for prompt in entry.get("prompts", []):
                label, typ, choices, default = prompt
                if typ == "select":
                    val = questionary.select(label + ":", choices=choices, default=default).ask()
                elif typ == "int":
                    val = int(questionary.text(label + ":", default=str(default)).ask())
                elif typ == "float":
                    val = float(questionary.text(label + ":", default=str(default)).ask())
                else:
                    val = questionary.text(label + ":", default=str(default)).ask()
                params.append(val)
            result = entry["func"](logs, *params)
            analytics_last = result
            analytics_type_last = analytics_action
            analytics_headers_last = entry["headers"]
            analytics_summary_last = None
            if "summary" in entry:
                summary_vals = entry["summary"](logs)
                if summary_vals:
                    avg, min_d, max_d = summary_vals
                    analytics_summary_last = f"Average: {avg:.2f} s, Min: {min_d:.2f} s, Max: {max_d:.2f} s" if avg is not None else "No durations available."
            print(f"\n{analytics_action}:")
            print(render_table(result, entry["headers"]))
            if analytics_summary_last:
                print(analytics_summary_last)
        elif analytics_action == "Export last analytics report (JSON)":
            if analytics_last is None:
                print("No analytics report to export yet.")
            else:
                export_path = questionary.text("Export analytics report to file:", default="analytics_report.json").ask()
                with open(export_path, 'w') as f:
                    json.dump({"type": analytics_type_last, "data": analytics_last, "headers": analytics_headers_last, "summary": analytics_summary_last}, f, indent=2)
                print(f"Analytics report exported to {export_path}")
        elif analytics_action == "Export last analytics report (Markdown)":
            if analytics_last is None:
                print("No analytics report to export yet.")
            else:
                export_path = questionary.text("Export analytics report to file:", default="analytics_report.md").ask()
                export_markdown(analytics_headers_last, analytics_last, analytics_type_last, export_path, summary=analytics_summary_last)
        elif analytics_action == "Back to main menu":
            break

def log_monitoring_feature():
    print("\n🦖 Log Monitoring & Search 🦖\n")
    log_file = questionary.text("Path to log file:", default=LOG_FILE).ask()
    logs = parse_logs(log_file)
    if not logs:
        print("No logs found.")
        return
    # Submenu for filtering
    while True:
        action = questionary.select(
            "Select log filter/search option:",
            choices=[
                "Filter by log level",
                "Filter by feature/module",
                "Filter by correlation ID",
                "Filter by time frame",
                "Show summary",
                "Export filtered logs",
                "Analytics & Reports",
                "Exit log monitoring"
            ]
        ).ask()
        level = feature = correlation_id = start_time = end_time = None
        filtered = logs
        if action == "Filter by log level":
            level = questionary.select("Select log level:", choices=["INFO", "ERROR", "WARNING", "DEBUG"]).ask()
            filtered = filter_logs(logs, level=level)
        elif action == "Filter by feature/module":
            features = sorted(set(log.get('feature', 'N/A') for log in logs))
            feature = questionary.select("Select feature:", choices=features).ask()
            filtered = filter_logs(logs, feature=feature)
        elif action == "Filter by correlation ID":
            corr_ids = sorted(set(log.get('correlation_id', 'N/A') for log in logs if log.get('correlation_id')))
            if not corr_ids:
                print("No correlation IDs found in logs.")
                continue
            correlation_id = questionary.select("Select correlation ID:", choices=corr_ids).ask()
            filtered = filter_logs(logs, correlation_id=correlation_id)
        elif action == "Filter by time frame":
            start_time = questionary.text("Start time (YYYY-MM-DD HH:MM:SS):", default="").ask()
            end_time = questionary.text("End time (YYYY-MM-DD HH:MM:SS):", default="").ask()
            filtered = filter_logs(logs, start_time=start_time or None, end_time=end_time or None)
        elif action == "Show summary":
            print(f"Total log entries: {len(logs)}")
            levels = {}
            features = {}
            for log in logs:
                lvl = log.get('levelname', 'N/A')
                feat = log.get('feature', 'N/A')
                levels[lvl] = levels.get(lvl, 0) + 1
                features[feat] = features.get(feat, 0) + 1
            print("Log entries by level:")
            for lvl, count in levels.items():
                print(f"  {lvl}: {count}")
            print("Log entries by feature:")
            for feat, count in features.items():
                print(f"  {feat}: {count}")
            continue
        elif action == "Export filtered logs":
            export_path = questionary.text("Export filtered logs to file:", default="filtered_logs.json").ask()
            with open(export_path, 'w') as f:
                json.dump(filtered, f, indent=2)
            print(f"Filtered logs exported to {export_path}")
            continue
        elif action == "Analytics & Reports":
            analytics_menu(logs)
            continue
        elif action == "Exit log monitoring":
            print("Exiting log monitoring.")
            break
        # Show filtered logs (if not summary/export/exit/analytics)
        if action.startswith("Filter"):
            print(f"\nFiltered log entries: {len(filtered)}\n")
            for log in filtered[:50]:  # Show up to 50 entries
                print(json.dumps(log, indent=2))
            if len(filtered) > 50:
                print(f"... {len(filtered)-50} more entries not shown ...")


def main():
    parser = argparse.ArgumentParser(description="Jirassic Pack Log Monitoring Utility")
    parser.add_argument('--log-file', type=str, default=LOG_FILE, help='Path to the log file')
    parser.add_argument('--correlation-id', type=str, help='Filter logs by correlation ID')
    parser.add_argument('--level', type=str, help='Filter logs by level (INFO, ERROR, etc.)')
    args = parser.parse_args()

    logs = parse_logs(args.log_file)
    if args.correlation_id:
        logs = [log for log in logs if log.get('correlation_id') == args.correlation_id]
    if args.level:
        logs = [log for log in logs if log.get('levelname', '').upper() == args.level.upper()]

    for log in logs:
        print(json.dumps(log, indent=2))

    # TODO: Add monitoring/alerting logic (e.g., error rate, anomaly detection, etc.)

if __name__ == '__main__':
    main() 