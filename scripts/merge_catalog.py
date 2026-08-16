#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def release_key(item: dict) -> tuple:
    return (
        item.get("packageName"),
        int(item.get("versionCode", 0)),
        item.get("signerSha256"),
        item.get("apkSha256"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scan", type=Path)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()

    scan = load(args.scan, {"apps": []})
    catalog = load(args.catalog, {"schemaVersion": 1, "apps": []})

    by_key = {release_key(item): item for item in catalog.get("apps", [])}
    for item in scan.get("apps", []):
        by_key[release_key(item)] = item

    apps = sorted(by_key.values(), key=lambda x: (x.get("packageName", ""), int(x.get("versionCode", 0))))
    args.catalog.parent.mkdir(parents=True, exist_ok=True)
    args.catalog.write_text(json.dumps({"schemaVersion": 1, "apps": apps}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Catalog now contains {len(apps)} release record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
