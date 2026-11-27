"""Append missing local keys without displaying or replacing existing values."""

import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

path = Path(__file__).resolve().parents[1] / ".env"
existing = path.read_text() if path.exists() else ""
known = {line.split("=", 1)[0].strip() for line in existing.splitlines() if "=" in line}
values = {
    "FOOD_TRACKER_ACCESS_JWT_SECRET": secrets.token_urlsafe(48),
    "FOOD_TRACKER_REFRESH_JWT_SECRET": secrets.token_urlsafe(48),
    "FOOD_TRACKER_CODE_HMAC_SECRET": secrets.token_urlsafe(48),
    "FOOD_TRACKER_CSRF_SECRET": secrets.token_urlsafe(48),
    "FOOD_TRACKER_MAIL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
}
missing = {key: value for key, value in values.items() if key not in known}
if missing:
    if path.exists():
        path.chmod(0o600)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as file:
        file.write("\n" + "".join(f"{key}={value}\n" for key, value in missing.items()))
    path.chmod(0o600)
print(f"Local auth configured: {len(missing)} missing keys added. Existing values preserved.")
