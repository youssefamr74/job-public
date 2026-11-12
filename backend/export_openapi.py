"""Writes the API schema to web/openapi.json, for `npm run gen:api` in web/."""

import json
from pathlib import Path

from main import app

target = Path(__file__).resolve().parent.parent / "web" / "openapi.json"
target.write_text(json.dumps(app.openapi(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {target}")
