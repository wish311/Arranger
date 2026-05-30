from __future__ import annotations

import re
from typing import Any

ALIASES = {
    "children": {"children", "childrens", "kids", "kid"},
    "kids": {"children", "childrens", "kids", "kid"},
    "family": {"family"},
    "animation": {"animation", "animated"},
    "animated": {"animation", "animated"},
}


def normalize_token(value: str) -> str:
    return value.strip().casefold()


def expand_alias(value: str) -> set[str]:
    normalized = normalize_token(value)
    return ALIASES.get(normalized, {normalized})


def any_token_matches(expected: list[str], actual: list[str | int]) -> bool:
    actual_values: set[str] = set()
    for item in actual:
        actual_values.update(expand_alias(str(item)))
    return any(expand_alias(item) & actual_values for item in expected)


def regex_matches(pattern: str | None, title: str) -> bool:
    return bool(pattern and re.search(pattern, title, re.IGNORECASE))


def path_contains(needles: list[str], path: str) -> bool:
    lower = path.casefold()
    return any(needle.casefold() in lower for needle in needles)


def custom_fields_match(expected: dict[str, Any], raw: dict[str, Any]) -> bool:
    return all(raw.get(key) == value for key, value in expected.items())
