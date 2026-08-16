from scripts.merge_firmware_sources import merge_sources


def test_merge_sources_deduplicates_by_url_and_preserves_known_metadata():
    existing = {
        "sources": [
            {"url": "https://example.com/a.zip", "brand": "TECNO", "device": "Old Name", "note": "keep"}
        ]
    }
    discovered = {
        "sources": [
            {"url": "https://example.com/a.zip", "brand": "TECNO", "device": "POVA", "region": "IN"},
            {"url": "https://example.com/b.zip", "brand": "Infinix", "device": "GT"},
        ]
    }
    merged = merge_sources(existing, discovered)
    assert len(merged["sources"]) == 2
    first = next(item for item in merged["sources"] if item["url"].endswith("a.zip"))
    assert first["device"] == "POVA"
    assert first["note"] == "keep"
