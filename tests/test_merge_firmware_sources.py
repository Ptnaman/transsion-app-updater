from scripts.merge_firmware_sources import merge_sources


def test_merge_sources_refreshes_url_for_same_firmware_and_preserves_metadata():
    existing = {
        "sources": [
            {
                "url": "https://example.com/old-token.zip",
                "brand": "TECNO",
                "device": "Old Name",
                "codename": "LJ8k",
                "region": "IN",
                "sourceBuild": "BUILD-1",
                "note": "keep",
            }
        ]
    }
    discovered = {
        "sources": [
            {
                "url": "https://example.com/new-token.zip",
                "brand": "TECNO",
                "device": "POVA Curve 5G",
                "codename": "LJ8k",
                "region": "IN",
                "sourceBuild": "BUILD-1",
            },
            {
                "url": "https://example.com/b.zip",
                "brand": "Infinix",
                "device": "GT",
                "codename": "X6871",
                "region": "IN",
                "sourceBuild": "BUILD-2",
            },
        ]
    }
    merged = merge_sources(existing, discovered)
    assert len(merged["sources"]) == 2
    first = next(item for item in merged["sources"] if item["codename"] == "LJ8k")
    assert first["url"] == "https://example.com/new-token.zip"
    assert first["device"] == "POVA Curve 5G"
    assert first["note"] == "keep"
