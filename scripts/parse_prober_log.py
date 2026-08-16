#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEVICE_RE = re.compile(r"^.*Device:\s*(.*?)\s*\(([^()]+)\)\s*$")
REGION_RE = re.compile(r"^.*(?:Variant / Region|Region):\s*.*?\(([A-Z0-9_-]{2,12})\)\s*$")
BUILD_RE = re.compile(r"^.*Build:\s*(\S+)\s*$")
TITLE_RE = re.compile(r"^.*New OTA update found:\s*(.+?)\s*$")
URL_RE = re.compile(r"^.*URL:\s*(https?://\S+)\s*$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def normalize_brand(fingerprint: str | None) -> str | None:
    if not fingerprint:
        return None
    oem = fingerprint.split("/", 1)[0].strip().lower()
    if "tecno" in oem:
        return "TECNO"
    if "infinix" in oem:
        return "Infinix"
    return None


def parse_log(text: str) -> list[dict]:
    current: dict[str, str | None] = {
        "device": None,
        "codename": None,
        "region": None,
        "fingerprint": None,
        "title": None,
    }
    records: list[dict] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = ANSI_RE.sub("", raw_line).strip()
        if not line:
            continue
        match = DEVICE_RE.match(line)
        if match:
            current["device"] = match.group(1).strip()
            current["codename"] = match.group(2).strip()
            current["region"] = None
            current["fingerprint"] = None
            current["title"] = None
            continue
        match = REGION_RE.match(line)
        if match:
            current["region"] = match.group(1).strip()
            continue
        match = BUILD_RE.match(line)
        if match:
            current["fingerprint"] = match.group(1).strip()
            continue
        match = TITLE_RE.match(line)
        if match:
            current["title"] = match.group(1).strip()
            continue
        match = URL_RE.match(line)
        if not match:
            continue

        url = match.group(1).strip()
        brand = normalize_brand(current.get("fingerprint"))
        if brand is None or url in seen:
            continue
        seen.add(url)
        records.append(
            {
                "url": url,
                "brand": brand,
                "device": current.get("device"),
                "codename": current.get("codename"),
                "region": current.get("region"),
                "sourceBuild": current.get("title"),
                "sourceFingerprint": current.get("fingerprint"),
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse dry-run output from transsion-ota-prober")
    parser.add_argument("log", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    records = parse_log(args.log.read_text(encoding="utf-8", errors="replace"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"schemaVersion": 1, "sources": records}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Discovered {len(records)} TECNO/Infinix firmware source(s)")
    return 0 if records else 2


if __name__ == "__main__":
    raise SystemExit(main())
