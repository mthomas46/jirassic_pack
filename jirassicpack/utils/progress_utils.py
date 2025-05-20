"""
Progress bar and spinner utilities for Jirassic Pack CLI.
Handles progress display and spinners for long-running operations.
"""
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from contextlib import contextmanager
import time

@contextmanager
def spinner(message: str):
    print(f"⏳ {message}")
    try:
        yield
    finally:
        print("✔️ Done.")

def progress_bar(iterable, desc="Progress"):
    total = len(iterable) if hasattr(iterable, '__len__') else None
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(desc, total=total)
        for index, element in enumerate(iterable, 1):
            progress.update(task, completed=index)
            yield element 