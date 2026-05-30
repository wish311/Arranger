import pytest

from arranger.clients.radarr import RadarrClient
from arranger.config import AppConfig, ArrConfig, RuleConfig, RulesConfig, Settings
from arranger.database import Database
from arranger.models import MoveStatus
from arranger.rules.engine import RuleEngine
from arranger.services.audit import AuditService


class FakeRadarr:
    moved = False

    async def list_movies(self):
        return [
            {
                "id": 1,
                "title": "Finding Nemo",
                "path": "/media/movies/general/Finding Nemo",
                "rootFolderPath": "/media/movies/general",
                "genres": ["Animation"],
                "certification": "PG",
                "hasFile": True,
            }
        ]

    async def get_rootfolders(self):
        return [{"path": "/media/movies/kids"}]

    async def get_queue(self):
        return {"records": []}

    def to_media_item(self, movie):
        return RadarrClient(ArrConfig(url="http://example", api_key="x")).to_media_item(movie)

    async def move_movie_to_root(self, movie_id, target_root):
        self.moved = True
        raise AssertionError("dry-run must not call move")


@pytest.mark.asyncio
async def test_dry_run_blocks_real_move(tmp_path) -> None:
    settings = Settings(
        app=AppConfig(dry_run=True, database_path=str(tmp_path / "arranger.db")),
        rules=RulesConfig(
            radarr=[
                RuleConfig(
                    name="Kids",
                    priority=1,
                    match_genres=["animation"],
                    target_root="/media/movies/kids",
                )
            ]
        ),
    )
    fake = FakeRadarr()
    audit = AuditService(
        settings, Database(settings.app.database_path), RuleEngine(settings.rules), radarr=fake
    )  # type: ignore[arg-type]
    result = await audit.audit_radarr()
    assert result["results"][0]["status"] == MoveStatus.DRY_RUN.value
    assert not fake.moved


@pytest.mark.asyncio
async def test_unknown_api_schema_blocks_real_move(monkeypatch) -> None:
    client = RadarrClient(ArrConfig(url="http://example", api_key="x"))

    async def fake_get_movie(movie_id: int):
        return {"id": movie_id, "title": "Bad Schema"}

    async def fake_roots():
        return [{"path": "/target"}]

    monkeypatch.setattr(client, "get_movie", fake_get_movie)
    monkeypatch.setattr(client, "get_rootfolders", fake_roots)
    result = await client.move_movie_to_root(1, "/target")
    await client.close()
    assert not result.success
    assert result.status == MoveStatus.FAILED
    assert "schema" in result.reason.casefold()
