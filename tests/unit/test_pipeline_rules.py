"""Pipeline value rules (`crm_app.domains.pipelines`; decision P4, slice 4A)."""

from __future__ import annotations

import pytest

from crm_app.domains import pipelines as rules
from crm_app.domains.records import InvalidValue


def test_names_are_trimmed_and_bounded() -> None:
    assert rules.pipeline_name("  Sales ") == "Sales"
    assert rules.stage_name(" Proposal ") == "Proposal"
    assert rules.pipeline_name("x" * 60) == "x" * 60
    assert rules.stage_name("Démo 张伟") == "Démo 张伟"


@pytest.mark.parametrize(
    "value",
    ["", "   ", "x" * 41, "a\tb", "a\nb", "a\u200bb", "a\u2028b"],
    ids=["empty", "blank", "long", "tab", "newline", "zero-width", "line-separator"],
)
def test_stage_names_outside_the_rules_are_refused(value: str) -> None:
    with pytest.raises(InvalidValue):
        rules.stage_name(value)


def test_a_pipeline_name_is_at_most_60_characters() -> None:
    with pytest.raises(InvalidValue):
        rules.pipeline_name("x" * 61)


@pytest.mark.parametrize("value", [0, 1, 50, 100])
def test_probabilities_are_whole_percentages(value: int) -> None:
    assert rules.probability(value) == value


@pytest.mark.parametrize("value", [-1, 101, True])
def test_probabilities_outside_0_to_100_are_refused(value: int) -> None:
    with pytest.raises(InvalidValue):
        rules.probability(value)


def test_the_default_stages_fit_the_rules() -> None:
    names = [name for name, _ in rules.DEFAULT_STAGES]
    assert len(set(map(str.lower, names))) == len(names) <= rules.MAX_STAGES
    for name, probability in rules.DEFAULT_STAGES:
        assert rules.stage_name(name) == name
        assert rules.probability(probability) == probability
    assert rules.pipeline_name(rules.DEFAULT_PIPELINE_NAME) == rules.DEFAULT_PIPELINE_NAME
