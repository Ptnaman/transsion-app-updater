from scripts.parse_prober_log import parse_log


def test_parse_prober_log_filters_itel_and_keeps_transsion_sources():
    log = """
Device: TECNO POVA Curve 5G (LJ8k)
Region: India (IN)
Build: TECNO/LJ8k-IN/TECNO-LJ8k:15/ABC/123:user/release-keys
New OTA update found: Tcard_LJ8k-16.3.0.145-IN001PF001AZ_a15
Size: 4 GB
URL: https://example.com/tecno.zip
Device: Infinix GT 20 Pro (X6871)
Variant / Region: India (IN)
Build: Infinix/X6871-IN/Infinix-X6871:15/ABC/456:user/release-keys
New OTA update found: Tcard_X6871-15.0.3.126-IN001PF001AZ
URL: https://example.com/infinix.zip
Device: itel S25 (S685LN)
Region: Global (OP)
Build: itel/S685LN-OP/itel-S685LN:15/ABC/789:user/release-keys
New OTA update found: Tcard_S685LN-test
URL: https://example.com/itel.zip
"""
    records = parse_log(log)
    assert [r["brand"] for r in records] == ["TECNO", "Infinix"]
    assert records[0]["codename"] == "LJ8k"
    assert records[0]["region"] == "IN"
    assert records[1]["sourceBuild"] == "Tcard_X6871-15.0.3.126-IN001PF001AZ"
