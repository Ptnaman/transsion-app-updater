from scanner.scan_apks import parse_badging, parse_signer_sha256


def test_parse_badging():
    text = """package: name='com.transsion.demo' versionCode='123' versionName='1.2.3' platformBuildVersionName='14'\nsdkVersion:'29'\ntargetSdkVersion:'34'\n"""
    got = parse_badging(text)
    assert got == {
        "packageName": "com.transsion.demo",
        "versionCode": 123,
        "versionName": "1.2.3",
        "minSdk": 29,
        "targetSdk": 34,
    }


def test_parse_signer_sha256_contiguous():
    digest = "11" * 32
    text = f"Signer #1 certificate SHA-256 digest: {digest}"
    got = parse_signer_sha256(text)
    assert got == ":".join(["11"] * 32)


def test_parse_signer_sha256_colon_separated_without_signer_prefix():
    digest = ":".join(["AB"] * 32)
    text = f"certificate SHA-256 digest: {digest}"
    assert parse_signer_sha256(text) == digest


def test_parse_signer_sha256_space_separated():
    digest = " ".join(["cd"] * 32)
    text = f"Certificate SHA-256 digest: {digest}"
    assert parse_signer_sha256(text) == ":".join(["CD"] * 32)


def test_parse_signer_sha256_fallback_on_sha256_line():
    digest = "EF" * 32
    text = f"SHA-256 certificate fingerprint {digest}"
    assert parse_signer_sha256(text) == ":".join(["EF"] * 32)
