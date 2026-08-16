#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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


def is_http_source(source: str) -> bool:
    return urlparse(source).scheme.lower() in {"http", "https"}


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


def payload_partition_names(payload: str | Path) -> set[str]:
    if shutil.which("payload-dumper") is None:
        raise IngestError("payload-dumper is required to inspect/extract payload firmware")
    proc = run(["payload-dumper", "list", str(payload), "--json"])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise IngestError("payload-dumper returned invalid partition JSON") from exc
    if not isinstance(data, dict):
        raise IngestError("payload-dumper partition output was not a JSON object")
    return set(data.keys())


def choose_app_partitions(available: set[str]) -> list[str]:
    wanted: list[str] = []
    for prefix in APP_PARTITIONS:
        for name in sorted(available):
            base = name[:-2] if name.endswith(("_a", "_b")) else name
            if base == prefix and name not in wanted:
                wanted.append(name)
    return wanted


def extract_payload_partition(payload: str | Path, partition: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    run(
        [
            "payload-dumper",
            "extract",
            str(payload),
            "--out",
            str(dest),
            "--partitions",
            partition,
            "--workers",
            "2",
            "--http-workers",
            "4",
            "--http-cache-size",
            "64M",
            "--max-buffer-mb",
            "64",
        ]
    )


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


def safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "unknown"


def stage_apks(source_root: Path, staging_root: Path, namespace: str) -> int:
    count = 0
    namespace_root = staging_root / safe_component(namespace)
    for apk in collect_apks(source_root):
        relative = apk.relative_to(source_root)
        target = namespace_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            stem, suffix = target.stem, target.suffix
            index = 2
            while target.exists():
                target = target.with_name(f"{stem}-{index}{suffix}")
                index += 1
        shutil.copy2(apk, target)
        count += 1
    return count


def process_partition_image(
    image: Path,
    partition: str,
    partition_work: Path,
    staging_root: Path,
    report: dict,
    *,
    streamed: bool,
) -> int:
    filesystem_dir = partition_work / "filesystem"
    raw_dir = partition_work / "raw"
    fs_type = extract_partition_image(image, filesystem_dir, raw_dir)
    apk_count = stage_apks(filesystem_dir, staging_root, partition)
    report["partitions"].append(
        {
            "name": partition,
            "filesystem": fs_type,
            "apkCount": apk_count,
            "streamed": streamed,
        }
    )
    return apk_count


def process_payload_source(
    payload: str | Path,
    workdir: Path,
    staging_root: Path,
    report: dict,
    *,
    label: str,
    streamed: bool,
) -> int:
    available = payload_partition_names(payload)
    selected = choose_app_partitions(available)
    if not selected:
        raise IngestError(f"No app-bearing partitions found in {label}")

    report["payloads"].append(
        {
            "label": label,
            "partitions": selected,
            "streamed": streamed,
        }
    )

    total = 0
    for partition in selected:
        partition_work = workdir / "partition-work" / f"{safe_component(label)}-{safe_component(partition)}"
        shutil.rmtree(partition_work, ignore_errors=True)
        images_dir = partition_work / "images"
        try:
            extract_payload_partition(payload, partition, images_dir)
            images = discover_partition_images(images_dir)
            if not images:
                raise IngestError(f"payload-dumper produced no supported image for {partition}")
            for image in images:
                total += process_partition_image(
                    image,
                    partition,
                    partition_work,
                    staging_root,
                    report,
                    streamed=streamed,
                )
        except Exception as exc:
            report["failures"].append(
                {
                    "stage": "payload-partition",
                    "label": label,
                    "partition": partition,
                    "error": str(exc),
                }
            )
        finally:
            # Keep only staged APKs and compact JSON reports. Large images/filesystems are disposable.
            shutil.rmtree(partition_work, ignore_errors=True)
    return total


def unpack_downloaded_source(source_path: Path, unpacked: Path) -> None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract and stage APKs from Android firmware/OTA packages")
    parser.add_argument("source", help="Local firmware path or HTTP(S) URL")
    parser.add_argument("--workdir", type=Path, default=Path("firmware-work"))
    parser.add_argument("--output", type=Path, default=Path("ingest-result.json"))
    args = parser.parse_args()

    workdir = args.workdir.resolve()
    downloads = workdir / "downloads"
    unpacked = workdir / "unpacked"
    staging_root = workdir / "apks"
    for directory in (downloads, unpacked, staging_root):
        directory.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "schemaVersion": 2,
        "source": args.source,
        "mode": None,
        "payloads": [],
        "partitions": [],
        "failures": [],
        "apkCount": 0,
        "apkRoot": str(staging_root),
    }

    total_apks = 0

    # Fast path for modern A/B OTA packages: payload-dumper-go can read HTTP(S) OTA ZIP URLs
    # directly using range requests. This avoids keeping the full 7-10 GB OTA ZIP on the runner.
    if is_http_source(args.source):
        try:
            payload_partition_names(args.source)
        except Exception as exc:
            report["failures"].append(
                {
                    "stage": "remote-payload-probe",
                    "error": str(exc),
                    "fallback": "full-download",
                }
            )
        else:
            report["mode"] = "streamed-payload"
            try:
                total_apks += process_payload_source(
                    args.source,
                    workdir,
                    staging_root,
                    report,
                    label="remote-ota",
                    streamed=True,
                )
            except Exception as exc:
                report["failures"].append({"stage": "remote-payload", "error": str(exc)})
            report["apkCount"] = total_apks
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"Streamed firmware ingestion found {total_apks} APK(s); {len(report['failures'])} failure(s).")
            return 0 if total_apks else 3

    # Fallback for non-payload firmware containers and local files/directories.
    report["mode"] = "download-and-unpack" if is_http_source(args.source) else "local-unpack"
    try:
        source_path = download_source(args.source, downloads)
        unpack_downloaded_source(source_path, unpacked)
    except Exception as exc:
        report["failures"].append({"stage": "source", "error": str(exc)})
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 2

    # APKs may exist directly in a vendor archive without partition images.
    total_apks += stage_apks(unpacked, staging_root, "direct")

    payloads = sorted(p for p in unpacked.rglob("payload.bin") if p.is_file())
    for index, payload in enumerate(payloads):
        try:
            total_apks += process_payload_source(
                payload,
                workdir,
                staging_root,
                report,
                label=f"payload-{index}",
                streamed=False,
            )
        except Exception as exc:
            report["failures"].append(
                {"stage": "payload", "path": str(payload), "error": str(exc)}
            )

    # Some firmware archives contain system/product/vendor images directly instead of payload.bin.
    for index, image in enumerate(discover_partition_images(unpacked)):
        partition = normalize_partition_name(image) or image.stem
        partition_work = workdir / "partition-work" / f"standalone-{index}-{safe_component(partition)}"
        shutil.rmtree(partition_work, ignore_errors=True)
        try:
            total_apks += process_partition_image(
                image,
                partition,
                partition_work,
                staging_root,
                report,
                streamed=False,
            )
        except Exception as exc:
            report["failures"].append(
                {"stage": "partition", "path": str(image), "error": str(exc)}
            )
        finally:
            shutil.rmtree(partition_work, ignore_errors=True)

    report["apkCount"] = len(collect_apks(staging_root))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Firmware ingestion staged {report['apkCount']} APK(s); {len(report['failures'])} failure(s).")
    return 0 if report["apkCount"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
