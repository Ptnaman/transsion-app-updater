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


def test_parse_signer_sha256():
    digest = "11" * 32
    text = f"Signer #1 certificate SHA-256 digest: {digest}"
    got = parse_signer_sha256(text)
    assert got == ":".join(["11"] * 32)
