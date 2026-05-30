from __future__ import annotations

import logging

from arranger.config import RuleConfig, RulesConfig
from arranger.models import MediaItem, RuleMatch
from arranger.rules.matchers import (
    any_token_matches,
    custom_fields_match,
    path_contains,
    regex_matches,
)

LOG = logging.getLogger(__name__)


class RuleEngine:
    def __init__(self, rules: RulesConfig) -> None:
        self.rules_config = rules

    def match(self, app: str, item: MediaItem) -> RuleMatch:
        rules = self.rules_config.radarr if app == "radarr" else self.rules_config.sonarr
        explicit = [rule for rule in rules if not rule.default and self._matches(rule, item)]
        if explicit:
            return self._select(explicit, item)
        defaults = [rule for rule in rules if rule.default]
        if not defaults:
            return RuleMatch(False, reason="No matching rule and no default rule configured")
        return self._select(defaults, item)

    def _select(self, rules: list[RuleConfig], item: MediaItem) -> RuleMatch:
        ordered = sorted(rules, key=lambda r: r.priority, reverse=True)
        top_priority = ordered[0].priority
        winners = [r for r in ordered if r.priority == top_priority]
        if len(winners) > 1 and not self.rules_config.allow_first_equal_priority_match:
            names = ", ".join(rule.name for rule in winners)
            LOG.warning("Rule conflict for %s: %s", item.title, names)
            return RuleMatch(
                False, reason=f"Conflicting equal-priority rules: {names}", conflict=True
            )
        winner = winners[0]
        return RuleMatch(True, winner.name, winner.target_root, f"Matched rule {winner.name}")

    def _matches(self, rule: RuleConfig, item: MediaItem) -> bool:
        checks: list[bool] = []
        if rule.match_genres:
            checks.append(any_token_matches(rule.match_genres, item.genres))
        if rule.match_tags:
            checks.append(any_token_matches(rule.match_tags, item.tags))
        if rule.match_certifications:
            checks.append(any_token_matches(rule.match_certifications, [item.certification or ""]))
        if rule.title_regex:
            checks.append(regex_matches(rule.title_regex, item.title))
        if rule.monitored is not None:
            checks.append(item.monitored is rule.monitored)
        if rule.path_contains:
            checks.append(path_contains(rule.path_contains, item.path))
        if rule.match_fields:
            checks.append(custom_fields_match(rule.match_fields, item.raw))
        return bool(checks) and all(checks)
