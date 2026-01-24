import os
import sys


def _warn(msg: str):
    """Write a yellow warning message to stderr with optional color (if TTY)."""
    use_color = sys.stderr.isatty() or os.environ.get("FORCE_COLOR", "")
    if use_color:
        sys.stderr.write(f"\033[33m{msg}\033[0m\n")
    else:
        sys.stderr.write(f"{msg}\n")


def _error(msg: str):
    """Write a red error message to stderr with optional color (if TTY)."""
    use_color = sys.stderr.isatty() or os.environ.get("FORCE_COLOR", "")
    if use_color:
        sys.stderr.write(f"\033[31m{msg}\033[0m\n")
    else:
        sys.stderr.write(f"{msg}\n")
