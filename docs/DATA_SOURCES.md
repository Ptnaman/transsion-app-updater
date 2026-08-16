# Data-source strategy

## Tier 1: OEM firmware extraction

Best source for preloaded TECNO/Infinix apps that are not published in an app store. The scanner should receive APK files only after firmware extraction. Firmware extraction adapters are intentionally separate from the metadata scanner because Transsion packages can use different container formats.

Store provenance with every record: brand, model, codename, region and source build.

## Tier 2: Official store metadata

Use official store listings for package identity and current public releases where available. Treat store downloading/redistribution as a separate licensing and delivery question.

## Tier 3: Trusted manual samples

A manually supplied APK may seed the catalog if its package identity, signer digest and file SHA-256 are captured. Never mark an unknown-signature build as a safe update.

## Community submissions

Accept metadata first. If APK submission is ever enabled, quarantine it and require signer + hash verification before publication.

## What the catalog should NOT do

- Do not choose an update solely because its version string looks newer.
- Do not mix APKs signed with different certificates under one compatible update path.
- Do not assume an APK extracted from one model is safe for every model.
- Do not commit OEM APK binaries to this Git repository.
