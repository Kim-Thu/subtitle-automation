import os
import threading
from pathlib import PurePosixPath, PureWindowsPath

# Global lock for clearer console output
print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)

def normalize_relative_path(path: str) -> str:
    """Normalize an untrusted relative path and reject traversal/absolute forms."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Path must be a non-empty relative path")

    raw = path.strip()
    normalized = raw.replace("\\", "/")

    if PurePosixPath(normalized).is_absolute() or PureWindowsPath(raw).is_absolute():
        raise ValueError("Absolute paths are not allowed")

    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        raise ValueError("Path traversal is not allowed")

    safe_parts = [part for part in parts if part not in ("", ".")]
    if not safe_parts:
        raise ValueError("Path must contain a valid name")

    return os.path.join(*safe_parts)

def resolve_managed_path(root: str, relative_path: str) -> str:
    """Resolve a user-controlled relative path and ensure it stays under root."""
    root_abs = os.path.abspath(root)
    normalized = normalize_relative_path(relative_path)
    candidate = os.path.abspath(os.path.join(root_abs, normalized))

    try:
        contained = os.path.commonpath([root_abs, candidate]) == root_abs
    except ValueError:
        contained = False

    if not contained:
        raise ValueError("Path escapes the managed directory")

    return candidate

def format_timestamp(seconds: float):
    from datetime import timedelta
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
