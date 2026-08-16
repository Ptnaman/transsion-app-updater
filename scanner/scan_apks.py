#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class ApkRecord:
    packageName: str
    versionName: str | None
    versionCode: int
    minSdk: int | None
    targetSdk: int | None
    signerSha256: str
    apkSha256: str
    fileName: str
    brand: str | None
    device: str | None
    codename: str | None
    region: str | None
    sourceBuild: str | None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout + ("\n" + proc.stderr if proc.stderr else "")


def parse_badging(text: str) -> dict[str, str | int | None]:
    pkg = re.search(r"package: name='([^']+)'(?:\s+versionCode='([^']+)')?(?:\s+versionName='([^']*)')?", text)
    if not pkg:
        raise ValueError("Could not parse package metadata from aapt2 output")

    min_sdk = re.search(r"sdkVersion:'(\d+)'", text)
    target_sdk = re.search(r"targetSdkVersion:'(\d+)'", text)
    return {
        "packageName": pkg.group(1),
        "versionCode": int(pkg.group(2) or 0),
        "versionName": pkg.group(3) or None,
        "minSdk": int(min_sdk.group(1)) if min_sdk else None,
        "targetSdk": int(target_sdk.group(1)) if target_sdk else None,
    }


def parse_signer_sha256(text: str) -> str:
    match = re.search(r"Signer #\d+ certificate SHA-256 digest:\s*([0-9A-Fa-f:]+)", text)
    if not match:
        raise ValueError("Could not parse signer SHA-256 from apksigner output")
    raw = re.sub(r"[^0-9A-Fa-f]", "", match.group(1)).upper()
    if len(raw) != 64:
        raise ValueError(f"Unexpected signer SHA-256 length: {len(raw)}")
    return ":".join(raw[i : i + 2] for i in range(0, len(raw), 2))


def scan_apk(path: Path, args: argparse.Namespace) -> ApkRecord:
    badging = parse_badging(_run(["aapt2", "dump", "badging", str(path)]))
    signer = parse_signer_sha256(_run(["apksigner", "verify", "--print-certs", str(path)]))
    return ApkRecord(
        packageName=str(badging["packageName"]),
        versionName=badging["versionName"],
        versionCode=int(badging["versionCode"]),
        minSdk=badging["minSdk"],
        targetSdk=badging["targetSdk"],
        signerSha256=signer,
        apkSha256=sha256_file(path),
        fileName=path.name,
        brand=args.brand,
        device=args.device,
        codename=args.codename,
        region=args.region,
        sourceBuild=args.build,
    )


def iter_apks(root: Path) -> Iterable[Path]:
    if root.is_file() and root.suffix.lower() == ".apk":
        yield root
        return
    yield from sorted(p for p in root.rglob("*.apk") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan APK metadata for the Transsion app catalog")
    parser.add_argument("input", type=Path)
    parser.add_argument("--brand")
    parser.add_argument("--device")
    parser.add_argument("--codename")
    parser.add_argument("--region")
    parser.add_argument("--build")
    parser.add_argument("--output", type=Path, default=Path("scan-result.json"))
    args = parser.parse_args()

    missing = [tool for tool in ("aapt2", "apksigner") if shutil.which(tool) is None]
    if missing:
        raise SystemExit(f"Missing Android Build Tools on PATH: {', '.join(missing)}")

    apks = list(iter_apks(args.input))
    if not apks:
        raise SystemExit(f"No APK files found under {args.input}")

    results: list[dict] = []
    failures: list[dict[str, str]] = []
    for apk in apks:
        try:
            results.append(asdict(scan_apk(apk, args)))
        except Exception as exc:
            failures.append({"file": str(apk), "error": str(exc)})

    payload = {"schemaVersion": 1, "apps": results, "failures": failures}
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Scanned {len(results)} APK(s); {len(failures)} failure(s). Output: {args.output}")
    return 1 if failures and not results else 0


if __name__ == "__main__":
    raise SystemExit(main())
