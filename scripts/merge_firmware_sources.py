#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_codename(value: object) -> str:
    text = str(value or "").strip()
    lower = text.lower()
    for prefix in ("tecno-", "infinix-", "itel-"):
        if lower.startswith(prefix):
            return text[len(prefix) :]
    return text


def normalize_item(item: dict) -> dict:
    normalized = dict(item)
    codename = normalize_codename(normalized.get("codename"))
    if codename:
        normalized["codename"] = codename
    return normalized


def source_key(item: dict) -> tuple[str, ...]:
    item = normalize_item(item)
    stable = (
        str(item.get("brand") or ""),
        str(item.get("codename") or ""),
        str(item.get("region") or ""),
        str(item.get("sourceBuild") or ""),
    )
    if any(stable):
        return ("firmware",) + stable
    return ("url", str(item.get("url") or ""))


def merge_sources(existing: dict, discovered: dict) -> dict:
    by_key: dict[tuple[str, ...], dict] = {}
    for raw_item in existing.get("sources", []):
        item = normalize_item(raw_item)
        if item.get("url"):
            by_key[source_key(item)] = item
    for raw_item in discovered.get("sources", []):
        item = normalize_item(raw_item)
        if not item.get("url"):
            continue
        key = source_key(item)
        previous = by_key.get(key, {})
        merged = {**previous, **{k: v for k, v in item.items() if v is not None}}
        by_key[key] = merged
    sources = sorted(
        by_key.values(),
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
    print(f"Firmware source catalog contains {len(merged['sources'])} firmware record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
