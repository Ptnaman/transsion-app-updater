from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(os.getenv("CATALOG_PATH", "data/catalog.json"))


@lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return payload.get("apps", [])


def releases_for(package_name: str) -> list[dict]:
    return sorted(
        (x for x in load_catalog() if x.get("packageName") == package_name),
        key=lambda x: int(x.get("versionCode", 0)),
        reverse=True,
    )
