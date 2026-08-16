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


def test_queue_can_filter_exact_codename():
    sources = {
        "sources": [
            source("X6871", 3000),
            source("X6896", 5000),
        ]
    }
    selected = select_next(sources, {"records": {}}, codename="x6896")
    assert selected is not None
    assert selected["codename"] == "X6896"


def test_queue_can_filter_codename_and_region():
    sources = {
        "sources": [
            source("X6896", 5000, region="OP", build="OP-BUILD"),
            source("X6896", 6000, region="IN", build="IN-BUILD"),
        ]
    }
    selected = select_next(sources, {"records": {}}, codename="X6896", region="IN")
    assert selected is not None
    assert selected["region"] == "IN"
    assert selected["sourceBuild"] == "IN-BUILD"


def test_queue_returns_none_when_filtered_codename_is_missing():
    sources = {"sources": [source("X6871", 3000)]}
    assert select_next(sources, {"records": {}}, codename="X6896") is None


def test_small_incremental_ota_is_opt_in():
    item = source("X6885", 98.3, region="OP", build="16.3.0-SP17")
    sources = {"sources": [item]}

    assert select_next(sources, {"records": {}}, codename="X6885", region="OP") is None

    selected = select_next(
        sources,
        {"records": {}},
        codename="X6885",
        region="OP",
        allow_small=True,
    )
    assert selected is not None
    assert selected["codename"] == "X6885"
    assert selected["sizeMb"] == 98.3
