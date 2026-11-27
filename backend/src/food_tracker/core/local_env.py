"""Atomic local .env updates for setup commands; values are never printed."""

import os
import re
import tempfile
from pathlib import Path


def update_env(path: Path, values: dict[str, str]) -> None:
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlinked .env")
    if any("\n" in v or "\r" in v for v in values.values()):
        raise ValueError("Environment values must fit on one line")
    current = path.read_text() if path.exists() else ""
    remaining = dict(values)

    def assignment(key, value):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"{key}='{escaped}'\n"

    lines = []
    for line in current.splitlines(keepends=True):
        match = re.match(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", line)
        if match and match[1] in values:
            if match[1] in remaining:
                lines.append(assignment(match[1], remaining.pop(match[1])))
        else:
            lines.append(line)
    if lines and not lines[-1].endswith("\n"):
        lines.append("\n")
    lines.extend(assignment(key, value) for key, value in remaining.items())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".env.", delete=False
        ) as file:
            temporary = Path(file.name)
            file.write("".join(lines))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
