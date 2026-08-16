# Transsion App Updater

Backend + scanner foundation for tracking TECNO and Infinix system-app versions without mixing this project into the OTA prober.

## Goal

Build a catalog of system-app releases from trusted inputs, then let an Android client compare the phone's installed package/version/signing certificate with the catalog before offering an update.

## Architecture

```text
TECNO / Infinix firmware or trusted APK input
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

## Why this split?

- `scanner/`: extracts package name, version name, version code, min/target SDK, APK hash and signer certificate digest.
- `data/catalog.json`: small metadata catalog only. Do **not** commit proprietary APK binaries.
- `app/`: read-only API for app/update lookup.
- Android client can later query this API and use Android `PackageInstaller` for user-approved installs.

## Data sources

Preferred order:

1. Original TECNO/Infinix firmware packages you are legally allowed to analyze.
2. Official Play Store releases for Transsion apps (metadata/link only unless redistribution is permitted).
3. Manually verified OEM APK samples.
4. Community submissions only after hash/signing checks.

Do not blindly trust a higher version number. The package name and signing certificate lineage must be compatible with the installed app.

## Local scan

Requirements:

- Python 3.11+
- Android SDK Build Tools available on PATH (`aapt2` and `apksigner`)

```bash
python scanner/scan_apks.py ./input-apks \
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

## Roadmap

- [x] APK metadata scanner
- [x] catalog merge tool
- [x] update-check API
- [x] GitHub Actions scanner validation
- [ ] firmware extractor adapters (payload.bin / super.img / product.img)
- [ ] official Play metadata adapter
- [ ] Android Kotlin updater client
- [ ] split-APK/APKS support
- [ ] trusted community submission pipeline
- [ ] release notifications
