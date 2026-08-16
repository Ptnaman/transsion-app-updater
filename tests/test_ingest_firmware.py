from pathlib import Path
import zipfile

import pytest

from firmware.ingest_firmware import (
    IngestError,
    choose_app_partitions,
    filesystem_type,
    is_http_source,
    is_sparse_image,
    safe_extract_zip,
    stage_apks,
)


def test_choose_app_partitions_only_app_bearing_partitions():
    available = {"boot", "system_a", "system_ext", "product", "vendor_b", "vbmeta"}
    assert choose_app_partitions(available) == ["system_a", "system_ext", "product", "vendor_b"]


def test_http_source_detection():
    assert is_http_source("https://example.com/ota.zip")
    assert is_http_source("http://example.com/ota.zip")
    assert not is_http_source("/tmp/ota.zip")
    assert not is_http_source("file:///tmp/ota.zip")


def test_stage_apks_preserves_relative_paths(tmp_path: Path):
    source = tmp_path / "fs"
    apk = source / "product" / "priv-app" / "Launcher" / "Launcher.apk"
    apk.parent.mkdir(parents=True)
    apk.write_bytes(b"fake-apk")

    staging = tmp_path / "staging"
    assert stage_apks(source, staging, "product") == 1
    staged = staging / "product" / "product" / "priv-app" / "Launcher" / "Launcher.apk"
    assert staged.read_bytes() == b"fake-apk"


def test_image_magic_detection(tmp_path: Path):
    sparse = tmp_path / "sparse.img"
    sparse.write_bytes(b"\x3a\xff\x26\xed" + b"\0" * 2048)
    assert is_sparse_image(sparse)

    erofs = tmp_path / "erofs.img"
    data = bytearray(2048)
    data[1024:1028] = b"\xe2\xe1\xf5\xe0"
    erofs.write_bytes(data)
    assert filesystem_type(erofs) == "erofs"

    ext = tmp_path / "ext.img"
    data = bytearray(2048)
    data[1080:1082] = b"\x53\xef"
    ext.write_bytes(data)
    assert filesystem_type(ext) == "ext"


def test_zip_slip_is_rejected(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", "nope")
    with pytest.raises(IngestError):
        safe_extract_zip(archive, tmp_path / "out")
