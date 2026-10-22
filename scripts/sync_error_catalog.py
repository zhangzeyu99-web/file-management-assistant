"""Update the web's public error catalog from the backend's reviewed messages."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.user_errors import catalog


def main():
    destination = ROOT / "web/lib/error-catalog.json"
    destination.write_text(json.dumps(catalog(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Updated web/lib/error-catalog.json")


if __name__ == "__main__":
    main()
