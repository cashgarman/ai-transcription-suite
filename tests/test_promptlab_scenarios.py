from speaker_transcriber.promptlab.scenarios import (
    MEETING_KINDS,
    build_freeform_scenario,
    build_scenario,
    kind_ids,
    scenario_content_key,
    suggested_style,
)
from speaker_transcriber.promptlab.types import (
    FACT_KINDS,
    FREEFORM_MODE,
    GROUNDED_MODE,
    SALIENCE_LEVELS,
)


def test_same_seed_produces_identical_content():
    first = build_scenario(4242, kind_id="architecture_review", duration_minutes=45)
    second = build_scenario(4242, kind_id="architecture_review", duration_minutes=45)

    assert scenario_content_key(first) == scenario_content_key(second)
    assert [fact.text for fact in first.facts] == [fact.text for fact in second.facts]
    assert [p.name for p in first.participants] == [p.name for p in second.participants]


def test_different_seeds_produce_different_content():
    keys = {
        scenario_content_key(build_scenario(seed, kind_id="product_review"))
        for seed in range(8)
    }
    assert len(keys) > 1


def test_scenario_ids_are_unique_even_for_one_seed():
    first = build_scenario(7, kind_id="standup")
    second = build_scenario(7, kind_id="standup")
    assert first.scenario_id != second.scenario_id


def test_every_kind_builds_a_usable_scenario():
    for kind in MEETING_KINDS:
        scenario = build_scenario(11, kind_id=kind.kind_id, duration_minutes=60)
        assert scenario.participants
        assert scenario.topics
        assert scenario.facts
        assert scenario.style_id
        for fact in scenario.facts:
            assert fact.kind in FACT_KINDS
            assert fact.salience in SALIENCE_LEVELS
            assert fact.topic_id in {topic.topic_id for topic in scenario.topics}
            assert "{" not in fact.text


def test_fact_ids_are_unique():
    scenario = build_scenario(99, duration_minutes=90)
    ids = [fact.fact_id for fact in scenario.facts]
    assert len(ids) == len(set(ids))


def test_grounded_scenarios_plant_decisions_and_actions():
    scenario = build_scenario(3, kind_id="product_review", duration_minutes=60)
    kinds = {fact.kind for fact in scenario.facts}
    assert "decision" in kinds
    assert "action_item" in kinds
    assert any(fact.owner for fact in scenario.facts)


def test_freeform_scenarios_carry_no_ground_truth():
    scenario = build_freeform_scenario(5, kind_id="design_critique")
    assert scenario.mode == FREEFORM_MODE
    assert scenario.facts == ()
    assert scenario.distractors == ()
    assert scenario.participants
    assert scenario.topics


def test_grounded_mode_is_the_default():
    assert build_scenario(1).mode == GROUNDED_MODE


def test_longer_meetings_get_more_topics():
    short = build_scenario(21, kind_id="product_review", duration_minutes=15)
    long = build_scenario(21, kind_id="product_review", duration_minutes=120)
    assert len(long.topics) >= len(short.topics)


def test_suggested_style_is_known_for_every_kind():
    for kind_id in kind_ids():
        assert suggested_style(kind_id)


def test_total_weight_reflects_salience():
    scenario = build_scenario(31, kind_id="art_review")
    assert scenario.total_weight == sum(fact.weight for fact in scenario.facts)
    assert scenario.total_weight > 0
