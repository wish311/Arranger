from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from arranger.api.management import create_management_router
from arranger.api.routes import create_router
from arranger.api.ui import create_ui_router
from arranger.config import AppConfig, RuleConfig, RulesConfig, Settings
from arranger.database import Database
from arranger.models import AppName, MoveRecord, MoveStatus
from arranger.rules.engine import RuleEngine
from arranger.services.audit import AuditService
from arranger.services.health import HealthService
from arranger.services.moves import MoveExecutor


def build_app(tmp_path, dry_run: bool = True) -> FastAPI:
    app = FastAPI()
    settings = Settings(
        app=AppConfig(
            dry_run=dry_run,
            database_path=str(tmp_path / "arranger.db"),
            ui_auth_enabled=False,
        ),
        rules=RulesConfig(
            radarr=[
                RuleConfig(name="A", priority=10, match_genres=["Animation"], target_root="/kids"),
                RuleConfig(
                    name="B", priority=10, match_genres=["Animation"], target_root="/family"
                ),
            ]
        ),
    )
    db = Database(settings.app.database_path)
    app.state.settings = settings
    app.state.db = db
    app.state.audit_service = AuditService(settings, db, RuleEngine(settings.rules))
    app.state.move_executor = MoveExecutor(settings, db, None, None)
    app.state.health_service = HealthService(settings, db, None, None)
    app.state.radarr = None
    app.state.sonarr = None
    app.include_router(create_router())
    app.include_router(create_management_router())
    app.include_router(create_ui_router())
    return app


def test_ui_route_loads(tmp_path) -> None:
    client = TestClient(build_app(tmp_path))
    response = client.get("/ui")
    assert response.status_code == 200
    assert "Arranger" in response.text
    assert "Dashboard" in response.text


def test_config_api_redacts_api_keys(tmp_path) -> None:
    app = build_app(tmp_path)
    app.state.settings = Settings(
        app=AppConfig(database_path=str(tmp_path / "arranger.db")),
        radarr={"url": "http://radarr", "api_key": "abcdef123456xyz"},
    )
    client = TestClient(app)
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json()["radarr"]["api_key"] == "abcdef********xyz"


def test_test_connection_failure_returns_useful_error(tmp_path) -> None:
    client = TestClient(build_app(tmp_path))
    response = client.post(
        "/api/test/radarr",
        json={"url": "http://127.0.0.1:1", "api_key": "bad", "enabled": True},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "Radarr connection failed" in response.json()["error"]


def test_dry_run_disable_requires_confirmation_phrase(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "arranger.yaml"
    config_path.write_text("app:\n  dry_run: true\n")
    monkeypatch.setenv("ARRANGER_CONFIG", str(config_path))
    client = TestClient(build_app(tmp_path))
    response = client.post("/api/config", json={"config": {"app": {"dry_run": False}}})
    assert response.status_code == 400
    assert "ENABLE LIVE MOVES" in response.json()["detail"]


def test_rule_validation_detects_equal_priority_conflicts(tmp_path) -> None:
    client = TestClient(build_app(tmp_path))
    response = client.post(
        "/api/rules/validate",
        json={
            "app": "radarr",
            "rules": [
                {"name": "A", "priority": 10, "target_root": "/a", "match_genres": ["Family"]},
                {"name": "B", "priority": 10, "target_root": "/b", "match_genres": ["family"]},
            ],
        },
    )
    assert response.status_code == 200
    assert "both match" in response.json()["warnings"][0]


def test_target_root_validation_blocks_missing_root(tmp_path) -> None:
    client = TestClient(build_app(tmp_path))
    response = client.post(
        "/api/rules/validate",
        json={
            "app": "sonarr",
            "rootfolders": ["/media/tv/general"],
            "rules": [{"name": "Kids", "priority": 10, "target_root": "/media/tv/kids"}],
        },
    )
    assert response.status_code == 200
    assert any(
        "not in discovered root folders" in warning for warning in response.json()["warnings"]
    )


def test_queue_approve_blocked_when_dry_run_true(tmp_path) -> None:
    app = build_app(tmp_path, dry_run=True)
    record_id = app.state.db.add_move(
        MoveRecord(
            app=AppName.RADARR,
            media_id=1,
            title="Movie",
            current_path="/old/Movie",
            target_root="/new",
            matched_rule="Rule",
            status=MoveStatus.PENDING,
            reason="Pending approval",
        )
    )
    client = TestClient(app)
    response = client.post(f"/queue/{record_id}/approve")
    assert response.status_code == 409
    assert "Dry-run" in response.json()["detail"]
