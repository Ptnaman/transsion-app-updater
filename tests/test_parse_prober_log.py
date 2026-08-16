from scripts.parse_prober_log import parse_log


def test_parse_prober_log_filters_itel_normalizes_codename_and_keeps_size():
    log = """
Device: TECNO POVA Curve 5G (TECNO-LJ8k)
Region: India (IN)
Build: TECNO/LJ8k-IN/TECNO-LJ8k:15/ABC/123:user/release-keys
New OTA update found: Tcard_LJ8k-16.3.0.145-IN001PF001AZ_a15
Size: 4 GB
URL: https://example.com/tecno.zip
Device: Infinix GT 20 Pro (Infinix-X6871)
Variant / Region: India (IN)
Build: Infinix/X6871-IN/Infinix-X6871:15/ABC/456:user/release-keys
New OTA update found: Tcard_X6871-15.0.3.126-IN001PF001AZ
Size: 7130.8 MB
URL: https://example.com/infinix.zip
Device: itel S25 (itel-S685LN)
Region: Global (OP)
Build: itel/S685LN-OP/itel-S685LN:15/ABC/789:user/release-keys
New OTA update found: Tcard_S685LN-test
Size: 5 GB
URL: https://example.com/itel.zip
"""
    records = parse_log(log)
    assert [r["brand"] for r in records] == ["TECNO", "Infinix"]
    assert records[0]["codename"] == "LJ8k"
    assert records[0]["region"] == "IN"
    assert records[0]["sizeMb"] == 4096.0
    assert records[1]["codename"] == "X6871"
    assert records[1]["sizeMb"] == 7130.8
    assert records[1]["sourceBuild"] == "Tcard_X6871-15.0.3.126-IN001PF001AZ"
