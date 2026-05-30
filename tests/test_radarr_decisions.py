from arranger.config import AppConfig
from arranger.models import AppName, MediaItem
from arranger.safety.radarr import RadarrSafetyGate

MOVIE = MediaItem(AppName.RADARR, 9, "Nemo", "/media/movies/general/Nemo", downloaded=True)


def test_radarr_movie_allows_only_downloaded_and_queue_empty() -> None:
    gate = RadarrSafetyGate(AppConfig())
    assert gate.evaluate(
        MOVIE, "/media/movies/kids", [{"path": "/media/movies/kids"}], {"records": []}
    ).allowed
    not_downloaded = MediaItem(
        AppName.RADARR, 9, "Nemo", "/media/movies/general/Nemo", downloaded=False
    )
    assert not gate.evaluate(
        not_downloaded, "/media/movies/kids", [{"path": "/media/movies/kids"}], {"records": []}
    ).allowed
    assert not gate.evaluate(
        MOVIE,
        "/media/movies/kids",
        [{"path": "/media/movies/kids"}],
        {"records": [{"movieId": 9, "status": "downloading"}]},
    ).allowed


def test_invalid_target_root_blocks_move() -> None:
    gate = RadarrSafetyGate(AppConfig())
    result = gate.evaluate(MOVIE, "/missing", [{"path": "/media/movies/kids"}], {"records": []})
    assert not result.allowed
    assert "target root" in result.reason.casefold()
