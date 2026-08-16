from pathlib import Path
import zipfile

import pytest

from firmware.ingest_firmware import (
    IngestError,
    choose_app_partitions,
    filesystem_type,
    is_sparse_image,
    safe_extract_zip,
)


def test_choose_app_partitions_only_app_bearing_partitions():
    available = {"boot", "system", "system_ext", "product", "vendor", "vbmeta"}
    assert choose_app_partitions(available) == ["system", "system_ext", "product", "vendor"]


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
