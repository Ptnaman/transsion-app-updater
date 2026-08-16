#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def merge_sources(existing: dict, discovered: dict) -> dict:
    by_url: dict[str, dict] = {}
    for item in existing.get("sources", []):
        url = item.get("url")
        if url:
            by_url[url] = item
    for item in discovered.get("sources", []):
        url = item.get("url")
        if not url:
            continue
        previous = by_url.get(url, {})
        merged = {**previous, **{k: v for k, v in item.items() if v is not None}}
        by_url[url] = merged
    sources = sorted(
        by_url.values(),
        key=lambda item: (
            str(item.get("brand") or ""),
            str(item.get("device") or ""),
            str(item.get("region") or ""),
            str(item.get("sourceBuild") or ""),
            str(item.get("url") or ""),
        ),
    )
    return {"schemaVersion": 1, "sources": sources}


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge discovered firmware URLs into the source catalog")
    parser.add_argument("discovered", type=Path)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()

    existing = load(args.catalog, {"schemaVersion": 1, "sources": []})
    discovered = load(args.discovered, {"schemaVersion": 1, "sources": []})
    merged = merge_sources(existing, discovered)
    args.catalog.parent.mkdir(parents=True, exist_ok=True)
    args.catalog.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Firmware source catalog contains {len(merged['sources'])} URL(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
