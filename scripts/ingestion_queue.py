#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FULL_OTA_MIN_MB = 1000.0
MAX_ATTEMPTS = 3


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def firmware_identity(item: dict) -> str:
    stable = {
        "brand": str(item.get("brand") or ""),
        "codename": str(item.get("codename") or ""),
        "region": str(item.get("region") or ""),
        "sourceBuild": str(item.get("sourceBuild") or ""),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def attempts_for(item: dict, state: dict) -> int:
    record = state.get("records", {}).get(firmware_identity(item), {})
    return int(record.get("attempts") or 0)


def is_eligible(item: dict, state: dict, *, max_attempts: int = MAX_ATTEMPTS) -> bool:
    if not item.get("url") or not item.get("brand") or not item.get("codename"):
        return False
    try:
        size_mb = float(item.get("sizeMb") or 0)
    except (TypeError, ValueError):
        return False
    # Small OTAs are usually incremental/delta packages and often need base images.
    if size_mb < FULL_OTA_MIN_MB:
        return False

    record = state.get("records", {}).get(firmware_identity(item), {})
    if record.get("status") == "success":
        return False
    if int(record.get("attempts") or 0) >= max_attempts:
        return False
    return True


def selection_key(item: dict) -> tuple:
    region = str(item.get("region") or "")
    region_rank = 0 if region == "IN" else 1 if region == "OP" else 2
    try:
        size_mb = float(item.get("sizeMb") or 0)
    except (TypeError, ValueError):
        size_mb = 10**9
    return (
        region_rank,
        size_mb,
        str(item.get("brand") or ""),
        str(item.get("device") or ""),
        str(item.get("sourceBuild") or ""),
    )


def select_next(
    sources: dict,
    state: dict,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    codename: str | None = None,
    region: str | None = None,
) -> dict | None:
    wanted_codename = (codename or "").strip().upper()
    wanted_region = (region or "").strip().upper()

    eligible = []
    for item in sources.get("sources", []):
        if wanted_codename and str(item.get("codename") or "").strip().upper() != wanted_codename:
            continue
        if wanted_region and str(item.get("region") or "").strip().upper() != wanted_region:
            continue
        if is_eligible(item, state, max_attempts=max_attempts):
            eligible.append(item)

    if not eligible:
        return None

    # Prefer never-tried firmware before retrying a failed source, so one broken
    # package cannot block the queue for multiple manual runs.
    selected = dict(
        sorted(
            eligible,
            key=lambda item: (attempts_for(item, state), selection_key(item)),
        )[0]
    )
    selected["firmwareId"] = firmware_identity(selected)
    return selected


def mark_state(state: dict, selected: dict, status: str, *, error: str | None = None) -> dict:
    if status not in {"success", "failed"}:
        raise ValueError("status must be success or failed")
    result = {
        "schemaVersion": 1,
        "records": dict(state.get("records", {})),
    }
    firmware_id = selected.get("firmwareId") or firmware_identity(selected)
    previous = dict(result["records"].get(firmware_id, {}))
    record = {
        **previous,
        "brand": selected.get("brand"),
        "device": selected.get("device"),
        "codename": selected.get("codename"),
        "region": selected.get("region"),
        "sourceBuild": selected.get("sourceBuild"),
        "sizeMb": selected.get("sizeMb"),
        "status": status,
        "attempts": int(previous.get("attempts") or 0) + 1,
        "lastAttemptAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if error:
        record["lastError"] = error[:1000]
    elif status == "success":
        record.pop("lastError", None)
    result["records"][firmware_id] = record
    return result


def cmd_select(args: argparse.Namespace) -> int:
    sources = load_json(args.sources, {"schemaVersion": 1, "sources": []})
    state = load_json(args.state, {"schemaVersion": 1, "records": {}})
    selected = select_next(
        sources,
        state,
        max_attempts=args.max_attempts,
        codename=args.codename,
        region=args.region,
    )
    if selected is None:
        if args.output.exists():
            args.output.unlink()
        filters = []
        if args.codename:
            filters.append(f"codename={args.codename}")
        if args.region:
            filters.append(f"region={args.region}")
        suffix = f" matching {', '.join(filters)}" if filters else ""
        print(f"No eligible full firmware source is waiting for ingestion{suffix}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Selected "
        f"{selected.get('brand')} {selected.get('device')} "
        f"{selected.get('region')} {selected.get('sourceBuild')} "
        f"({selected.get('sizeMb')} MB)"
    )
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    selected = load_json(args.selected, {})
    if not selected:
        raise SystemExit("Selected firmware JSON is empty")
    state = load_json(args.state, {"schemaVersion": 1, "records": {}})
    error = None
    if args.error_file and args.error_file.exists():
        error = args.error_file.read_text(encoding="utf-8", errors="replace")
    updated = mark_state(state, selected, args.status, error=error)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Marked {selected.get('firmwareId') or firmware_identity(selected)} as {args.status}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Select and track firmware ingestion jobs")
    sub = parser.add_subparsers(dest="command", required=True)

    select = sub.add_parser("select")
    select.add_argument("sources", type=Path)
    select.add_argument("state", type=Path)
    select.add_argument("output", type=Path)
    select.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS)
    select.add_argument("--codename", help="Only select this device codename, for example X6896")
    select.add_argument("--region", help="Only select this region, for example IN or OP")
    select.set_defaults(func=cmd_select)

    mark = sub.add_parser("mark")
    mark.add_argument("selected", type=Path)
    mark.add_argument("state", type=Path)
    mark.add_argument("--status", choices=["success", "failed"], required=True)
    mark.add_argument("--error-file", type=Path)
    mark.set_defaults(func=cmd_mark)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
