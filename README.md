# Transsion App Updater

Backend + scanner foundation for tracking TECNO and Infinix system-app versions without mixing this project into the OTA prober.

## Goal

Build a catalog of system-app releases from trusted firmware, then let an Android client compare the phone's installed package/version/signing certificate with the catalog before offering an update.

## Architecture

```text
Ptnaman/transsion-ota-prober (read-only discovery)
                  |
                  v
      data/firmware_sources.json
                  |
                  v
   firmware/ingest_firmware.py
   (ZIP/TAR -> payload.bin -> partition images)
                  |
                  v
      system/product/system_ext/vendor
          (EROFS or ext filesystem)
                  |
                  v
          scanner/scan_apks.py
     (aapt2 + apksigner + SHA-256)
                  |
                  v
            scan-result.json
                  |
                  v
         scripts/merge_catalog.py
                  |
                  v
           data/catalog.json
                  |
                  v
             FastAPI API
                  |
                  v
       Android updater client (next)
```

## What is automatic now?

### Firmware URL discovery

`.github/workflows/discover-firmware.yml` runs every 6 hours. It temporarily clones `Ptnaman/transsion-ota-prober`, runs it in `--dry-run --skip-telegram` mode, extracts TECNO/Infinix device/build/region/URL information from its output, and merges it into `data/firmware_sources.json`.

The OTA prober repository is read-only from this project. This workflow does not modify its configs, processed state, or Telegram setup.

### Firmware ingestion

`.github/workflows/ingest-firmware.yml` can be started manually with a direct public firmware/OTA URL plus device metadata. It:

1. downloads and safely unpacks ZIP/TAR firmware,
2. finds `payload.bin`,
3. extracts app-bearing partitions with `payload-dumper-go`,
4. converts Android sparse images with `simg2img`,
5. extracts EROFS or ext2/ext3/ext4 filesystem images,
6. scans every APK with `aapt2` and `apksigner`,
7. merges new releases into `data/catalog.json`,
8. commits only catalog metadata (never firmware/APK binaries),
9. stores scan reports as short-lived GitHub Actions artifacts.

Large firmware downloads are deliberately not auto-started for every discovery yet. A single modern OTA plus extracted partitions can consume substantial GitHub-hosted runner disk and bandwidth. First we validate real TECNO/Infinix packages, then the queue can safely auto-ingest a controlled number per run.

## Why this split?

- `firmware/`: turns firmware/OTA containers into APK-bearing filesystem trees.
- `scanner/`: extracts package name, version name, version code, min/target SDK, APK hash and signer certificate digest.
- `data/firmware_sources.json`: discovered firmware source metadata/URLs.
- `data/catalog.json`: small app-release metadata catalog only. Do **not** commit proprietary APK binaries.
- `app/`: read-only API for app/update lookup.
- Android client can later query this API and use Android `PackageInstaller` for user-approved installs.

## Data sources

Preferred order:

1. Original TECNO/Infinix firmware packages you are legally allowed to analyze.
2. Official Play Store releases for Transsion apps (metadata/link only unless redistribution is permitted).
3. Manually verified OEM APK samples.
4. Community submissions only after hash/signing checks.

Do not blindly trust a higher version number. The package name and signing certificate lineage must be compatible with the installed app.

## Local firmware ingestion

Host tools used by the ingestion pipeline:

- `payload-dumper` (`payload-dumper-go` v0.1.6 in GitHub Actions)
- `simg2img`
- `fsck.erofs`
- `debugfs`
- Android SDK Build Tools (`aapt2` and `apksigner`)

```bash
python firmware/ingest_firmware.py ./firmware.zip \
  --workdir firmware-work \
  --output ingest-result.json

python scanner/scan_apks.py firmware-work \
  --brand TECNO \
  --device "POVA Curve 5G" \
  --codename LJ8k \
  --region IN \
  --build "LJ8k-16.3.0.145(IN001PF001AZ)" \
  --output scan-result.json

python scripts/merge_catalog.py scan-result.json data/catalog.json
```

## API

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Endpoints:

- `GET /health`
- `GET /v1/apps`
- `GET /v1/apps/{package_name}`
- `POST /v1/check` — compare installed package/version/signer against catalog

Example check body:

```json
{
  "packageName": "com.transsion.example",
  "versionCode": 100,
  "signerSha256": "AA:BB:CC"
}
```

## Compatibility rules

An update is offered only when:

- same package name,
- catalog version code is greater than installed version code,
- signer SHA-256 matches the installed signer (strict mode),
- optional device/brand/region constraints match when present.

This project deliberately starts strict. A future Android client can support certificate rotation using Android's signing lineage APIs.

## Current firmware limitations

- Full OTA `payload.bin` is supported when its app-bearing partition images can be reconstructed without a base image.
- Incremental/delta payloads that require old partition images are not automatically reconstructed yet.
- Direct `super.img` extraction is not implemented yet; payload-based packages are the preferred path for now.
- Split APK/APKS packages are not cataloged yet.

## Roadmap

- [x] APK metadata scanner
- [x] catalog merge tool
- [x] update-check API
- [x] GitHub Actions scanner validation
- [x] firmware ZIP/TAR extractor
- [x] payload.bin app-partition extraction
- [x] Android sparse image conversion
- [x] EROFS + ext filesystem extraction
- [x] scheduled TECNO/Infinix OTA URL discovery (old prober stays read-only)
- [ ] validate first real firmware end-to-end
- [ ] controlled automatic firmware ingestion queue
- [ ] incremental OTA/base-image reconstruction
- [ ] direct super.img adapter
- [ ] official Play metadata adapter
- [ ] Android Kotlin updater client
- [ ] split-APK/APKS support
- [ ] trusted community submission pipeline
- [ ] release notifications
