# Transsion App Updater

Backend and scanner for tracking TECNO and Infinix system-app versions. This repository is intentionally separate from `Ptnaman/transsion-ota-prober`.

## Goal

Build a trusted catalog of Transsion system-app releases from OEM firmware, then let an Android client compare its installed package/version/signing certificate with the catalog before offering an update.

## Architecture

```text
Ptnaman/transsion-ota-prober (read-only dry-run discovery)
                  |
                  v
      data/firmware_sources.json
                  |
                  v
       controlled ingestion queue
                  |
                  v
   firmware/ingest_firmware.py
  (HTTP OTA -> selected payload partitions)
                  |
                  v
      system/product/system_ext/vendor
          (EROFS or ext filesystem)
                  |
                  v
       firmware-work/apks/ only
                  |
                  v
          scanner/scan_apks.py
     (aapt2 + apksigner + SHA-256)
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

## Automatic firmware discovery

`.github/workflows/discover-firmware.yml` runs every 6 hours. It temporarily clones `Ptnaman/transsion-ota-prober`, runs it with `--dry-run --skip-telegram`, parses only TECNO/Infinix results, and merges firmware metadata into `data/firmware_sources.json`.

The old OTA-prober repository is read-only from this project. Its configs, processed state and Telegram setup are not changed.

Discovery records include:

- brand
- device
- normalized codename
- region
- OTA/build title
- source fingerprint
- OTA size in MB
- direct source URL

## Low-disk streamed firmware ingestion

For modern payload-based HTTP OTA packages, `firmware/ingest_firmware.py` first asks `payload-dumper-go` to inspect the remote OTA directly. When supported, it does **not** save the complete multi-gigabyte OTA ZIP.

Instead it processes app-bearing partitions one at a time:

1. inspect remote payload partitions,
2. select `system`, `system_ext`, `product`, `vendor`, `odm`, `my_product` and `product_services` when present,
3. stream/extract one selected partition,
4. convert Android sparse images when required,
5. extract EROFS or ext2/ext3/ext4 filesystems,
6. copy only APKs into `firmware-work/apks/`,
7. delete the large temporary partition image/filesystem,
8. continue with the next partition.

For firmware formats that cannot be read as a remote payload, a download-and-unpack fallback remains available.

## APK scanning and compatibility data

`scanner/scan_apks.py` uses Android SDK `aapt2` and `apksigner` and records:

- package name
- version name
- version code
- min SDK / target SDK
- APK SHA-256
- signer certificate SHA-256
- source brand/device/codename/region/build

The updater must not trust only a higher version number. Package identity and signing compatibility are mandatory checks.

## Controlled automatic ingestion queue

`scripts/ingestion_queue.py` and `data/ingestion_state.json` prevent the same firmware from being processed repeatedly.

Current queue policy:

- prefers India (`IN`) sources, then global/other regions,
- ignores packages below 1000 MB for automatic ingestion because these are commonly incremental/delta OTAs,
- retries a failed firmware up to 3 times,
- permanently skips a firmware after successful ingestion unless its stable firmware identity changes,
- uses brand + codename + region + source build as the stable identity, so refreshed CDN URLs do not create duplicate work.

`.github/workflows/auto-ingest.yml` implements the full queue -> extract -> scan -> merge -> state flow. Its recurring schedule is intentionally kept disabled until the real streamed-firmware smoke test is green.

## GitHub Actions

- `test.yml` — Python unit tests.
- `discover-firmware.yml` — 6-hour read-only OTA discovery.
- `smoke-stream.yml` — real streamed partition validation against a known TECNO/Infinix full OTA.
- `ingest-firmware.yml` — manual full firmware ingestion with explicit device metadata.
- `auto-ingest.yml` — controlled queue worker; schedule enabled only after smoke validation.

All workflows that write repository data use a shared concurrency lock to avoid competing pushes to `main`.

## Data files

- `data/firmware_sources.json` — discovered firmware sources and metadata.
- `data/ingestion_state.json` — success/failure/attempt state for automatic ingestion.
- `data/catalog.json` — system-app release metadata.

Firmware ZIPs, partition images and APK binaries are ignored by Git and are not committed to this repository.

## Manual firmware ingestion

Host tools:

- `payload-dumper` (`payload-dumper-go` v0.1.6)
- `simg2img`
- `fsck.erofs`
- `debugfs`
- Android SDK Build Tools (`aapt2`, `apksigner`)

```bash
python firmware/ingest_firmware.py "https://example.com/full-ota.zip" \
  --workdir firmware-work \
  --output ingest-result.json

python scanner/scan_apks.py firmware-work/apks \
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
- `POST /v1/check`

Example update check:

```json
{
  "packageName": "com.transsion.example",
  "versionCode": 100,
  "signerSha256": "AA:BB:CC"
}
```

## Update compatibility rules

An update is offered only when:

- package name matches,
- catalog `versionCode` is greater than the installed version,
- signer SHA-256 matches in strict mode,
- optional brand/device/region constraints match when present.

A future Android client can add Android signing-certificate lineage support for legitimate certificate rotation.

## Current limitations

- Full payload-based OTAs are the preferred automated source.
- Incremental/delta payloads that require old partition images are not automatically reconstructed yet.
- Direct `super.img` extraction is not implemented yet.
- Split APK/APKS packages are not cataloged yet.
- APK binary hosting/delivery is intentionally separate from this public metadata repository.

## Roadmap

- [x] APK metadata scanner
- [x] catalog merge tool
- [x] update-check API
- [x] test workflow
- [x] scheduled TECNO/Infinix OTA URL discovery
- [x] firmware ZIP/TAR fallback extractor
- [x] remote payload partition streaming
- [x] Android sparse image conversion
- [x] EROFS + ext filesystem extraction
- [x] controlled automatic ingestion queue/state
- [ ] pass first real streamed firmware partition smoke test
- [ ] enable recurring automatic ingestion worker
- [ ] incremental OTA/base-image reconstruction
- [ ] direct `super.img` adapter
- [ ] official Play metadata adapter
- [ ] Android Kotlin updater client
- [ ] split APK/APKS support
- [ ] trusted APK binary delivery/storage
- [ ] release notifications
