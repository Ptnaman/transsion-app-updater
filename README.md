# Transsion App Updater

Backend and scanner for tracking TECNO and Infinix system-app versions. This repository is intentionally separate from `Ptnaman/transsion-ota-prober`.

## Goal

Build a trusted catalog of Transsion system-app releases from OEM firmware, then let an Android client compare its installed package/version/signing certificate with the catalog before offering an update.

## Manual-only operating mode

Firmware discovery and firmware ingestion do **not** run on a schedule. They run only when the repository owner presses **Run workflow** in GitHub Actions.

Recommended manual flow:

1. Run `Discover firmware sources (manual)` when you want to refresh OTA URLs.
2. Run `Process next firmware (manual)` to automatically choose the next eligible full firmware from the source catalog.
3. Or run `Ingest firmware (manual)` when you want to provide an exact OTA URL/device/build yourself.
4. After a successful ingestion, download the `firmware-apks-<run id>` artifact from the workflow run page.

The APK artifact is retained for 7 days. APK binaries are not committed to the Git repository.

## Architecture

```text
Ptnaman/transsion-ota-prober (read-only dry-run discovery)
                  |
                  v
      data/firmware_sources.json
                  |
                  v
       manual ingestion trigger
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
       firmware-work/apks/
                  |
          +-------+--------+
          |                |
          v                v
 GitHub Actions       scanner/scan_apks.py
 APK artifact         metadata + signatures
                           |
                           v
                    data/catalog.json
```

## Firmware discovery

`.github/workflows/discover-firmware.yml` is manual-only. It temporarily clones `Ptnaman/transsion-ota-prober`, runs it with `--dry-run --skip-telegram`, parses TECNO/Infinix results, and merges firmware metadata into `data/firmware_sources.json`.

The old OTA-prober repository remains read-only from this project. Its configs, processed state and Telegram setup are not changed.

Discovery records include brand, device, normalized codename, region, OTA/build title, source fingerprint, OTA size and direct source URL.

## Low-disk firmware ingestion

For supported modern payload-based HTTP OTA packages, `firmware/ingest_firmware.py` does not need to save the complete multi-gigabyte OTA ZIP. It processes app-bearing partitions one at a time, extracts their filesystem, copies APKs into `firmware-work/apks/`, and deletes large temporary partition data before moving to the next partition.

App-bearing partitions currently include `system`, `system_ext`, `product`, `vendor`, `odm`, `my_product` and `product_services` when available.

A live GitHub Actions smoke test on an Infinix GT 20 Pro (`X6871`, India) OTA successfully streamed an 802.8 MB `system` partition and extracted 75 APKs.

## Where the APK files are

During a workflow run the extracted files are staged under:

```text
firmware-work/apks/
├── system/
├── system_ext/
├── product/
├── vendor/
├── odm/
└── ...
```

The original firmware directory structure is kept under each partition as much as possible. At the end of a successful manual ingestion, GitHub Actions uploads this folder as:

```text
firmware-apks-<run id>
```

To get the APKs: open the completed workflow run in **Actions**, scroll to **Artifacts**, and download `firmware-apks-<run id>`.

A separate `firmware-scan-<run id>` artifact contains JSON reports such as package/version/signing/hash metadata.

## APK scanning and compatibility data

`scanner/scan_apks.py` uses Android SDK `aapt2` and `apksigner` and records package name, version name, version code, min/target SDK, APK SHA-256, signer certificate SHA-256, source brand/device/codename/region/build.

Do not trust only a higher version number. Package identity and signing compatibility are mandatory checks before offering an update.

## Manual queue policy

`scripts/ingestion_queue.py` and `data/ingestion_state.json` prevent repeatedly processing the same firmware when `Process next firmware (manual)` is used.

Current policy prefers India sources, ignores packages below 1000 MB in the queue because these are commonly incremental/delta OTAs, prefers never-tried firmware before retries, retries a failed source up to 3 times, and skips a firmware after successful ingestion unless its stable identity changes.

## GitHub Actions

- `test.yml` — Python unit tests for code/test changes.
- `discover-firmware.yml` — manual OTA source discovery.
- `smoke-stream.yml` — manual real streamed-partition validation.
- `ingest-firmware.yml` — manual ingestion of an exact OTA URL with device metadata.
- `auto-ingest.yml` — despite the filename, this is now the **manual** `Process next firmware` queue worker.

## Data files

- `data/firmware_sources.json` — discovered firmware sources and metadata.
- `data/ingestion_state.json` — success/failure/attempt state for queue ingestion.
- `data/catalog.json` — system-app release metadata.

Firmware ZIPs, partition images and APK binaries are ignored by Git and are not committed to this repository.

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

## Current limitations

- Full payload-based OTAs are the preferred source.
- Incremental/delta payloads requiring old partition images are not reconstructed yet.
- Direct `super.img` extraction is not implemented yet.
- Split APK/APKS packages are not cataloged yet.
- APK artifacts are temporary GitHub Actions downloads, not permanent public hosting.

## Roadmap

- [x] APK metadata scanner
- [x] catalog merge tool
- [x] update-check API
- [x] firmware source discovery
- [x] remote payload partition streaming
- [x] sparse + EROFS + ext filesystem extraction
- [x] manual ingestion queue/state
- [x] real firmware partition smoke validation
- [x] export extracted APKs as downloadable workflow artifacts
- [ ] validate first full all-partition manual catalog ingestion
- [ ] incremental OTA/base-image reconstruction
- [ ] direct `super.img` adapter
- [ ] Android Kotlin updater client
- [ ] split-APK/APKS support
- [ ] permanent trusted APK delivery/storage
