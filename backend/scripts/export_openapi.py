"""Export the contract without connecting to PostgreSQL."""

import argparse
import json
from pathlib import Path

from food_tracker.main import create_app

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true", help="Fail if the saved contract is stale")
args = parser.parse_args()
path = Path(__file__).resolve().parents[1] / "openapi.json"
content = json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n"
if args.check:
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        raise SystemExit("OpenAPI is stale: run uv run python scripts/export_openapi.py")
    print("OpenAPI is up to date")
else:
    path.write_text(content, encoding="utf-8")
    print(path)
