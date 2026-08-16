from app.main import UpdateCheck, scope_matches


def test_scope_matches_region():
    release = {"brand": "TECNO", "region": "IN"}
    req = UpdateCheck(packageName="x", versionCode=1, signerSha256="AA", brand="tecno", region="in")
    assert scope_matches(release, req)


def test_scope_rejects_other_region():
    release = {"region": "IN"}
    req = UpdateCheck(packageName="x", versionCode=1, signerSha256="AA", region="EU")
    assert not scope_matches(release, req)
