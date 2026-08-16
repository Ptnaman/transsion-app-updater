from scripts.ingestion_queue import firmware_identity, mark_state, select_next


def source(device: str, size: float, region: str = "IN", build: str = "BUILD-1") -> dict:
    return {
        "url": f"https://example.com/{device}.zip",
        "brand": "TECNO",
        "device": device,
        "codename": device,
        "region": region,
        "sourceBuild": build,
        "sizeMb": size,
    }


def test_queue_prefers_india_then_smaller_full_ota():
    sources = {
        "sources": [
            source("large-in", 8000),
            source("small-in", 3000),
            source("small-op", 2000, region="OP"),
            source("incremental", 120),
        ]
    }
    selected = select_next(sources, {"records": {}})
    assert selected is not None
    assert selected["device"] == "small-in"


def test_queue_prefers_untried_source_before_retry():
    failed = source("failed-small", 1500)
    fresh = source("fresh-large", 5000, build="BUILD-2")
    state = mark_state({"records": {}}, failed, "failed", error="boom")
    selected = select_next({"sources": [failed, fresh]}, state)
    assert selected is not None
    assert selected["device"] == "fresh-large"


def test_successful_firmware_is_not_selected_again():
    item = source("done", 3000)
    state = mark_state({"records": {}}, item, "success")
    assert select_next({"sources": [item]}, state) is None


def test_failed_firmware_retries_only_up_to_limit():
    item = source("retry", 3000)
    state = {"records": {}}
    for _ in range(3):
        state = mark_state(state, item, "failed", error="boom")
    assert state["records"][firmware_identity(item)]["attempts"] == 3
    assert select_next({"sources": [item]}, state, max_attempts=3) is None
