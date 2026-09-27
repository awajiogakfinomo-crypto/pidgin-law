from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "static"
OUTPUT = ROOT / "dist"


def main() -> None:
    api_base_url = os.environ.get("API_BASE_URL", "").strip().rstrip("/")

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    shutil.copytree(SOURCE, OUTPUT)
    (OUTPUT / "static").mkdir()
    shutil.copytree(SOURCE / "css", OUTPUT / "static" / "css")
    shutil.copytree(SOURCE / "js", OUTPUT / "static" / "js")
    shutil.copytree(ROOT / "app" / "data", OUTPUT / "data")
    (OUTPUT / "config.js").write_text(
        "window.PIDGIN_LAW_API_BASE = "
        f"{json.dumps(api_base_url)};\n"
        f"window.PIDGIN_LAW_STATIC_MODE = {json.dumps(not bool(api_base_url))};\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()