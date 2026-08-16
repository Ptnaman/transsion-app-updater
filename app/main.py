from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.catalog import load_catalog, releases_for

app = FastAPI(title="Transsion App Updater API", version="0.1.0")


class UpdateCheck(BaseModel):
    packageName: str
    versionCode: int = Field(ge=0)
    signerSha256: str
    brand: str | None = None
    device: str | None = None
    codename: str | None = None
    region: str | None = None


def scope_matches(release: dict, req: UpdateCheck) -> bool:
    for field in ("brand", "device", "codename", "region"):
        expected = release.get(field)
        actual = getattr(req, field)
        if expected and actual and str(expected).casefold() != str(actual).casefold():
            return False
    return True


@app.get("/health")
def health() -> dict:
    return {"ok": True, "releases": len(load_catalog())}


@app.get("/v1/apps")
def apps() -> list[dict]:
    latest: dict[str, dict] = {}
    for release in load_catalog():
        package = release.get("packageName")
        if not package:
            continue
        if package not in latest or int(release.get("versionCode", 0)) > int(latest[package].get("versionCode", 0)):
            latest[package] = release
    return sorted(latest.values(), key=lambda x: x.get("packageName", ""))


@app.get("/v1/apps/{package_name}")
def app_releases(package_name: str) -> list[dict]:
    result = releases_for(package_name)
    if not result:
        raise HTTPException(status_code=404, detail="Package not found")
    return result


@app.post("/v1/check")
def check_update(req: UpdateCheck) -> dict:
    candidates = []
    for release in releases_for(req.packageName):
        if int(release.get("versionCode", 0)) <= req.versionCode:
            continue
        if str(release.get("signerSha256", "")).casefold() != req.signerSha256.casefold():
            continue
        if not scope_matches(release, req):
            continue
        candidates.append(release)

    if not candidates:
        return {"updateAvailable": False, "latest": None}
    return {"updateAvailable": True, "latest": candidates[0]}
