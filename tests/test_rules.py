from arranger.config import RuleConfig, RulesConfig
from arranger.models import AppName, MediaItem
from arranger.rules.engine import RuleEngine


def item(genres: list[str]) -> MediaItem:
    return MediaItem(
        AppName.RADARR,
        1,
        "Finding Nemo",
        "/media/movies/general/Finding Nemo",
        genres=genres,
        certification="PG",
    )


def test_genre_matching_is_case_insensitive() -> None:
    engine = RuleEngine(
        RulesConfig(
            radarr=[
                RuleConfig(
                    name="Kids", priority=10, match_genres=["Animation"], target_root="/kids"
                )
            ]
        )
    )
    match = engine.match("radarr", item(["animation"]))
    assert match.matched
    assert match.target_root == "/kids"


def test_kids_rule_beats_default_by_priority() -> None:
    engine = RuleEngine(
        RulesConfig(
            radarr=[
                RuleConfig(name="Default", priority=1, default=True, target_root="/general"),
                RuleConfig(
                    name="Kids", priority=100, match_genres=["Children"], target_root="/kids"
                ),
            ]
        )
    )
    match = engine.match("radarr", item(["Kids"]))
    assert match.rule_name == "Kids"


def test_conflicting_equal_priority_matches_are_blocked() -> None:
    engine = RuleEngine(
        RulesConfig(
            radarr=[
                RuleConfig(name="A", priority=10, match_genres=["Animation"], target_root="/a"),
                RuleConfig(name="B", priority=10, match_genres=["Family"], target_root="/b"),
            ]
        )
    )
    match = engine.match("radarr", item(["Animation", "Family"]))
    assert not match.matched
    assert match.conflict
