#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

APP_PARTITIONS = (
    "system",
    "system_ext",
    "product",
    "vendor",
    "odm",
    "my_product",
    "product_services",
)
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tgz", ".tar.gz", ".tar.xz", ".txz")
SPARSE_MAGIC = b"\x3a\xff\x26\xed"
EROFS_MAGIC = b"\xe2\xe1\xf5\xe0"
EXT_MAGIC = b"\x53\xef"


class IngestError(RuntimeError):
    pass


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise IngestError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{detail}")
    return proc


def _safe_target(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise IngestError(f"Archive member escapes destination: {relative}") from exc
    return target


def safe_extract_zip(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if not info.filename or info.filename.endswith("/"):
                continue
            target = _safe_target(dest, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)


def safe_extract_tar(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            if member.issym() or member.islnk() or member.isdev():
                continue
            _safe_target(dest, member.name)
        try:
            tf.extractall(dest, filter="data")
        except TypeError:  # Python < 3.12
            tf.extractall(dest)


def is_archive(path: Path) -> bool:
    name = path.name.lower()
    if path.suffix.lower() in {".apk", ".apks", ".xapk"}:
        return False
    if zipfile.is_zipfile(path):
        return True
    if any(name.endswith(suffix) for suffix in ARCHIVE_SUFFIXES):
        try:
            return tarfile.is_tarfile(path)
        except OSError:
            return False
    return False


def expand_archives(root: Path, *, max_rounds: int = 3) -> list[Path]:
    extracted: list[Path] = []
    seen: set[Path] = set()
    for round_no in range(max_rounds):
        archives = [p for p in root.rglob("*") if p.is_file() and p not in seen and is_archive(p)]
        if not archives:
            break
        for archive in archives:
            seen.add(archive)
            out = root / f"archive-{round_no}-{len(extracted)}-{archive.stem}"
            if zipfile.is_zipfile(archive):
                safe_extract_zip(archive, out)
            else:
                safe_extract_tar(archive, out)
            extracted.append(out)
    return extracted


def download_source(source: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        filename = Path(unquote(parsed.path)).name or "firmware.bin"
        target = dest_dir / filename
        req = urllib.request.Request(source, headers={"User-Agent": "transsion-app-updater/1.0"})
        with urllib.request.urlopen(req, timeout=60) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out, length=4 * 1024 * 1024)
        return target
    if parsed.scheme and parsed.scheme != "file":
        raise IngestError(f"Unsupported source scheme: {parsed.scheme}")
    local = Path(parsed.path if parsed.scheme == "file" else source).expanduser().resolve()
    if not local.exists():
        raise IngestError(f"Source does not exist: {local}")
    target = dest_dir / local.name
    if local.is_dir():
        target = dest_dir / "local-source"
        shutil.copytree(local, target, dirs_exist_ok=True)
    else:
        shutil.copy2(local, target)
    return target


def payload_partition_names(payload: Path) -> set[str]:
    if shutil.which("payload-dumper") is None:
        raise IngestError("payload-dumper is required to unpack payload.bin")
    proc = run(["payload-dumper", "list", str(payload), "--json"])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise IngestError("payload-dumper returned invalid partition JSON") from exc
    return set(data.keys())


def choose_app_partitions(available: set[str]) -> list[str]:
    wanted: list[str] = []
    for prefix in APP_PARTITIONS:
        for name in sorted(available):
            base = name[:-2] if name.endswith(("_a", "_b")) else name
            if base == prefix and name not in wanted:
                wanted.append(name)
    return wanted


def extract_payload(payload: Path, dest: Path) -> list[str]:
    available = payload_partition_names(payload)
    selected = choose_app_partitions(available)
    if not selected:
        raise IngestError(f"No app-bearing partitions found in {payload}")
    dest.mkdir(parents=True, exist_ok=True)
    run([
        "payload-dumper",
        "extract",
        str(payload),
        "--out",
        str(dest),
        "--partitions",
        ",".join(selected),
    ])
    return selected


def is_sparse_image(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) == SPARSE_MAGIC
    except OSError:
        return False


def filesystem_type(path: Path) -> str | None:
    try:
        with path.open("rb") as f:
            f.seek(1024)
            if f.read(4) == EROFS_MAGIC:
                return "erofs"
            f.seek(1080)
            if f.read(2) == EXT_MAGIC:
                return "ext"
    except OSError:
        return None
    return None


def normalize_partition_name(path: Path) -> str | None:
    name = path.name.lower()
    if not name.endswith(".img"):
        return None
    stem = name[:-4]
    if stem.endswith(("_a", "_b")):
        stem = stem[:-2]
    return stem if stem in APP_PARTITIONS else None


def extract_partition_image(image: Path, dest: Path, raw_dir: Path) -> str:
    source = image
    if is_sparse_image(image):
        if shutil.which("simg2img") is None:
            raise IngestError("simg2img is required for Android sparse images")
        raw_dir.mkdir(parents=True, exist_ok=True)
        source = raw_dir / f"{image.stem}.raw.img"
        run(["simg2img", str(image), str(source)])

    fs_type = filesystem_type(source)
    dest.mkdir(parents=True, exist_ok=True)
    if fs_type == "erofs":
        if shutil.which("fsck.erofs") is None:
            raise IngestError("fsck.erofs is required for EROFS images")
        run(["fsck.erofs", f"--extract={dest}", str(source)])
        return "erofs"
    if fs_type == "ext":
        if shutil.which("debugfs") is None:
            raise IngestError("debugfs is required for ext2/ext3/ext4 images")
        run(["debugfs", "-R", f"rdump / {dest}", str(source)])
        return "ext"
    raise IngestError(f"Unsupported or unknown filesystem image: {image.name}")


def discover_partition_images(root: Path) -> list[Path]:
    images: list[Path] = []
    seen: set[Path] = set()
    for path in root.rglob("*.img"):
        if not path.is_file() or normalize_partition_name(path) is None:
            continue
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            images.append(path)
    return sorted(images)


def collect_apks(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.apk") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract APK-bearing partitions from Android firmware/OTA packages")
    parser.add_argument("source", help="Local firmware path or HTTP(S) URL")
    parser.add_argument("--workdir", type=Path, default=Path("firmware-work"))
    parser.add_argument("--output", type=Path, default=Path("ingest-result.json"))
    args = parser.parse_args()

    workdir = args.workdir.resolve()
    downloads = workdir / "downloads"
    unpacked = workdir / "unpacked"
    payload_out = workdir / "payload"
    fs_out = workdir / "filesystems"
    raw_out = workdir / "raw"
    for directory in (downloads, unpacked, payload_out, fs_out, raw_out):
        directory.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "schemaVersion": 1,
        "source": args.source,
        "payloads": [],
        "partitions": [],
        "failures": [],
        "apkCount": 0,
        "apkRoot": str(workdir),
    }

    try:
        source_path = download_source(args.source, downloads)
        if source_path.is_dir():
            shutil.copytree(source_path, unpacked / source_path.name, dirs_exist_ok=True)
        elif is_archive(source_path):
            if zipfile.is_zipfile(source_path):
                safe_extract_zip(source_path, unpacked)
            else:
                safe_extract_tar(source_path, unpacked)
        else:
            shutil.copy2(source_path, unpacked / source_path.name)
        expand_archives(unpacked)
    except Exception as exc:
        report["failures"].append({"stage": "source", "error": str(exc)})
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 2

    payloads = sorted(p for p in unpacked.rglob("payload.bin") if p.is_file())
    for index, payload in enumerate(payloads):
        out = payload_out / f"payload-{index}"
        try:
            selected = extract_payload(payload, out)
            report["payloads"].append({"path": str(payload), "partitions": selected})
        except Exception as exc:
            report["failures"].append({"stage": "payload", "path": str(payload), "error": str(exc)})

    image_roots = [unpacked, payload_out]
    images: list[Path] = []
    seen_images: set[Path] = set()
    for root in image_roots:
        for image in discover_partition_images(root):
            resolved = image.resolve()
            if resolved not in seen_images:
                seen_images.add(resolved)
                images.append(image)

    for index, image in enumerate(images):
        partition = normalize_partition_name(image) or image.stem
        dest = fs_out / f"{index}-{partition}"
        try:
            fs_type = extract_partition_image(image, dest, raw_out)
            report["partitions"].append({"path": str(image), "name": partition, "filesystem": fs_type, "output": str(dest)})
        except Exception as exc:
            report["failures"].append({"stage": "partition", "path": str(image), "error": str(exc)})

    apks = collect_apks(workdir)
    report["apkCount"] = len(apks)
    report["apkRoot"] = str(workdir)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Firmware ingestion found {len(apks)} APK(s); {len(report['failures'])} failure(s).")
    return 0 if apks else 3


if __name__ == "__main__":
    raise SystemExit(main())
