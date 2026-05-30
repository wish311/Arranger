from datetime import UTC, datetime, timedelta

from arranger.config import AppConfig, SonarrMoveSafetyConfig
from arranger.models import AppName, MediaItem
from arranger.safety.sonarr import SonarrSafetyGate

ROOTS = [{"path": "/media/tv/kids"}]
SERIES = MediaItem(AppName.SONARR, 5, "Bluey", "/media/tv/general/Bluey", status="continuing")


def gate() -> SonarrSafetyGate:
    return SonarrSafetyGate(SonarrMoveSafetyConfig(delay_after_last_import_minutes=0), AppConfig())


def test_sonarr_active_queue_blocks_move() -> None:
    result = gate().evaluate(
        SERIES,
        "/media/tv/kids",
        ROOTS,
        {"records": [{"seriesId": 5, "status": "downloading"}]},
        [],
        [],
    )
    assert not result.allowed
    assert "queue" in result.reason.casefold()


def test_sonarr_missing_monitored_episodes_blocks_move() -> None:
    episodes = [
        {
            "monitored": True,
            "hasFile": False,
            "airDateUtc": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        }
    ]
    result = gate().evaluate(SERIES, "/media/tv/kids", ROOTS, {"records": []}, episodes, [])
    assert not result.allowed
    assert "missing" in result.reason.casefold()


def test_sonarr_all_available_episodes_allows_when_complete_and_queue_empty() -> None:
    episodes = [
        {
            "monitored": True,
            "hasFile": True,
            "airDateUtc": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
        {
            "monitored": True,
            "hasFile": False,
            "airDateUtc": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    ]
    result = gate().evaluate(SERIES, "/media/tv/kids", ROOTS, {"records": []}, episodes, [])
    assert result.allowed
