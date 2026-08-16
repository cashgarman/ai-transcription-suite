import json

import pytest

from promptlab_fakes import FakeOllamaClient
from speaker_transcriber.promptlab.judge import (
    JudgeSettings,
    claim_count,
    composite_for,
    document_headings,
    has_action_table,
    judge_run,
    parse_judge_json,
    precision_for,
    recall_for,
    structure_metrics,
)
from speaker_transcriber.promptlab.scenarios import build_scenario
from speaker_transcriber.promptlab.types import (
    FREEFORM_MODE,
    FactVerdict,
    GROUNDED_MODE,
    GeneratedTranscript,
    RubricScores,
    STATUS_COVERED,
    STATUS_MISSING,
    STATUS_PARTIAL,
    StructureMetrics,
    SummaryRun,
)


STYLE = "meeting_summary"


def _run(markdown: str = "# Notes\n\nBody.", **overrides) -> SummaryRun:
    fields = {
        "run_id": "run-1",
        "transcript_id": "txn-1",
        "scenario_id": "scn-1",
        "variant_id": "shipped",
        "variant_fingerprint": "abc",
        "style_id": STYLE,
        "model_name": "test-model",
        "num_ctx": 8192,
        "markdown": markdown,
    }
    fields.update(overrides)
    return SummaryRun(**fields)


def _transcript() -> GeneratedTranscript:
    return GeneratedTranscript(
        transcript_id="txn-1",
        scenario_id="scn-1",
        seed=1,
        mode=GROUNDED_MODE,
        style_id=STYLE,
        label="A meeting",
        generator_model="test-model",
        generator_num_ctx=8192,
        duration_seconds=120.0,
        word_count=300,
        transcript={
            "source_file": "a.wav",
            "language": "en",
            "duration_seconds": 120.0,
            "speakers": {"SPEAKER_00": "Ada B."},
            "segments": [
                {
                    "start": 0.0,
                    "end": 4.0,
                    "speaker": "SPEAKER_00",
                    "text": "We agreed to ship on Friday.",
                    "words": [],
                }
            ],
        },
    )


# Deterministic checks


def test_headings_are_extracted_in_order():
    markdown = "# Title\n\ntext\n\n## Decisions\n\n### Detail\n"
    assert document_headings(markdown) == ("Title", "Decisions", "Detail")


def test_an_owner_action_table_is_recognized():
    markdown = "## Action Items\n\n| Owner | Action | Due |\n| --- | --- | --- |\n| Ada | Ship | Fri |"
    assert has_action_table(markdown) is True


def test_prose_under_an_action_heading_is_not_a_table():
    assert has_action_table("## Action Items\n\n- Ada will ship it.\n") is False


def test_claim_count_scales_with_content():
    small = claim_count("One sentence.")
    large = claim_count("- a\n- b\n- c\n\nA sentence. Another one.")
    assert large > small >= 1


def test_missing_sections_are_reported():
    metrics = structure_metrics("# Meeting\n\nJust a paragraph.", STYLE)

    assert metrics.expected_headings
    assert metrics.missing_headings
    assert metrics.score < 1.0


def test_a_complete_document_scores_well():
    headings = "\n\n".join(
        f"## {heading}" for heading in structure_metrics("", STYLE).expected_headings
    )
    metrics = structure_metrics(
        headings
        + "\n\n| Owner | Action | Due |\n| --- | --- | --- |\n| Ada | Ship | Fri |",
        STYLE,
    )

    assert metrics.missing_headings == ()
    assert metrics.score == pytest.approx(1.0)


def test_an_excluded_section_that_appears_anyway_is_leakage():
    excluded = ("risks",)
    heading = "Risks, Dependencies, and Blockers"
    assert heading not in structure_metrics("", STYLE, excluded).expected_headings

    metrics = structure_metrics(f"## {heading}\n\nSomething risky.", STYLE, excluded)

    assert heading in metrics.leaked_headings
    assert metrics.score < 1.0


def test_word_and_heading_counts_are_recorded():
    metrics = structure_metrics("# One\n\nthree more words\n\n## Two\n", STYLE)
    assert metrics.heading_count == 2
    assert metrics.word_count == 7


# JSON parsing


def test_plain_json_parses():
    assert parse_judge_json('{"a": 1}') == {"a": 1}


def test_fenced_json_parses():
    assert parse_judge_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_json_wrapped_in_prose_parses():
    text = 'Here is my assessment:\n{"a": [1, 2]}\nHope that helps.'
    assert parse_judge_json(text) == {"a": [1, 2]}


def test_nested_objects_parse():
    payload = {"scores": {"faithfulness": 4}, "facts": [{"fact_id": "T1"}]}
    assert parse_judge_json(json.dumps(payload)) == payload


def test_braces_inside_strings_do_not_confuse_the_parser():
    assert parse_judge_json('{"note": "a } brace"}') == {"note": "a } brace"}


def test_empty_output_is_rejected():
    with pytest.raises(ValueError):
        parse_judge_json("   ")


def test_output_without_json_is_rejected():
    with pytest.raises(ValueError):
        parse_judge_json("I could not grade this.")


def test_an_unclosed_object_is_rejected():
    with pytest.raises(ValueError):
        parse_judge_json('{"a": 1')


# Scoring


def test_recall_weighs_salient_facts_more():
    scenario = build_scenario(5, kind_id="product_review", duration_minutes=30)
    core = [fact for fact in scenario.facts if fact.salience == "core"]
    minor = [fact for fact in scenario.facts if fact.salience == "incidental"]
    if not core or not minor:
        pytest.skip("This seed produced no mix of saliences.")

    covered_core = tuple(
        FactVerdict(fact.fact_id, STATUS_COVERED if fact in core else STATUS_MISSING)
        for fact in scenario.facts
    )
    covered_minor = tuple(
        FactVerdict(fact.fact_id, STATUS_COVERED if fact in minor else STATUS_MISSING)
        for fact in scenario.facts
    )

    assert recall_for(scenario, covered_core) > recall_for(scenario, covered_minor)


def test_partial_coverage_earns_half_credit():
    scenario = build_scenario(6, kind_id="standup", duration_minutes=15)
    partial = tuple(FactVerdict(fact.fact_id, STATUS_PARTIAL) for fact in scenario.facts)
    full = tuple(FactVerdict(fact.fact_id, STATUS_COVERED) for fact in scenario.facts)

    assert recall_for(scenario, full) == pytest.approx(1.0)
    assert recall_for(scenario, partial) == pytest.approx(0.5)


def test_recall_is_zero_when_nothing_was_carried():
    scenario = build_scenario(7, kind_id="standup")
    missing = tuple(FactVerdict(fact.fact_id, STATUS_MISSING) for fact in scenario.facts)
    assert recall_for(scenario, missing) == 0.0


def test_precision_is_perfect_without_unsupported_claims():
    assert precision_for("- one\n- two\n", (), ()) == 1.0


def test_a_distractor_costs_more_than_an_ordinary_overreach():
    markdown = "\n".join(f"- point {index}" for index in range(10))
    ordinary = precision_for(markdown, ("a claim",), ())
    distractor = precision_for(markdown, (), ("a rejected idea",))
    assert distractor < ordinary < 1.0


def test_precision_never_goes_negative():
    assert precision_for("- one", tuple(f"claim {n}" for n in range(50)), ()) == 0.0


def test_composite_stays_in_range_and_rewards_recall():
    rubric = RubricScores(4, 4, 4, 4, 4, 4)
    structure = StructureMetrics()
    low = composite_for(GROUNDED_MODE, 0.2, 0.9, rubric, structure)
    high = composite_for(GROUNDED_MODE, 0.9, 0.9, rubric, structure)

    assert 0.0 <= low <= high <= 1.0


def test_freeform_composite_ignores_recall():
    rubric = RubricScores(4, 4, 4, 4, 4, 4)
    structure = StructureMetrics()
    assert composite_for(FREEFORM_MODE, 0.0, 0.8, rubric, structure) == composite_for(
        FREEFORM_MODE, 1.0, 0.8, rubric, structure
    )


# End to end


def _grounded_payload(scenario, status=STATUS_COVERED):
    return json.dumps(
        {
            "facts": [
                {"fact_id": fact.fact_id, "status": status, "evidence": "quoted"}
                for fact in scenario.facts
            ],
            "unsupported_claims": [],
            "asserted_distractors": [],
            "scores": {
                "faithfulness": 5,
                "coverage": 4,
                "structure": 4,
                "attribution": 5,
                "concision": 3,
                "actionability": 4,
            },
            "notes": "Solid.",
        }
    )


def test_a_grounded_run_is_scored_fact_by_fact():
    scenario = build_scenario(11, kind_id="product_review", duration_minutes=30)
    client = FakeOllamaClient([_grounded_payload(scenario)])

    card = judge_run(
        _run(),
        _transcript(),
        scenario,
        JudgeSettings("judge-model"),
        client=client,
    )

    assert card.mode == GROUNDED_MODE
    assert card.recall == pytest.approx(1.0)
    assert card.precision == 1.0
    assert len(card.fact_verdicts) == len(scenario.facts)
    assert card.rubric.faithfulness == 5
    assert card.composite > 0.5
    assert card.error == ""


def test_facts_the_judge_ignored_count_as_missing():
    scenario = build_scenario(12, kind_id="standup", duration_minutes=15)
    partial = json.dumps(
        {
            "facts": [{"fact_id": scenario.facts[0].fact_id, "status": "covered"}],
            "scores": {"faithfulness": 4},
        }
    )
    client = FakeOllamaClient([partial])

    card = judge_run(
        _run(), _transcript(), scenario, JudgeSettings("judge-model"), client=client
    )

    assert len(card.fact_verdicts) == len(scenario.facts)
    assert card.fact_verdicts[0].status == STATUS_COVERED
    assert all(
        verdict.status == STATUS_MISSING for verdict in card.fact_verdicts[1:]
    )
    assert card.recall < 1.0


def test_malformed_output_triggers_one_repair_attempt():
    scenario = build_scenario(13, kind_id="standup", duration_minutes=15)
    client = FakeOllamaClient(["I think it was fine.", _grounded_payload(scenario)])

    card = judge_run(
        _run(), _transcript(), scenario, JudgeSettings("judge-model"), client=client
    )

    assert len(client.calls) == 2
    assert card.error == ""
    assert card.recall == pytest.approx(1.0)


def test_two_bad_responses_record_an_unjudgeable_run():
    scenario = build_scenario(14, kind_id="standup", duration_minutes=15)
    client = FakeOllamaClient(["nope", "still nope"])

    card = judge_run(
        _run(), _transcript(), scenario, JudgeSettings("judge-model"), client=client
    )

    assert card.error
    assert card.composite == 0.0
    assert card.structure.word_count > 0


def test_a_failed_run_is_scored_without_calling_the_model():
    scenario = build_scenario(15, kind_id="standup", duration_minutes=15)
    client = FakeOllamaClient([])

    card = judge_run(
        _run(markdown="", error="Ollama exploded"),
        _transcript(),
        scenario,
        JudgeSettings("judge-model"),
        client=client,
    )

    assert client.calls == []
    assert card.error == "Ollama exploded"
    assert all(v.status == STATUS_MISSING for v in card.fact_verdicts)


def test_a_freeform_run_is_graded_against_the_transcript():
    scenario = build_scenario(16, kind_id="team_sync", duration_minutes=20)
    freeform = json.dumps(
        {
            "unsupported_claims": ["The budget was doubled."],
            "missing_points": ["The decision about the wiki."],
            "scores": {"faithfulness": 2, "coverage": 3},
            "notes": "Invented a figure.",
        }
    )
    client = FakeOllamaClient([freeform])

    card = judge_run(
        _run(),
        _transcript(),
        None,
        JudgeSettings("judge-model"),
        client=client,
    )

    assert card.mode == FREEFORM_MODE
    assert card.recall == 0.0
    assert card.unsupported_claims == ("The budget was doubled.",)
    assert "Dropped:" in card.notes
    assert "We agreed to ship on Friday." in client.prompts[0]


def test_rubric_scores_are_clamped_to_the_scale():
    scenario = build_scenario(17, kind_id="standup", duration_minutes=15)
    client = FakeOllamaClient(
        [json.dumps({"facts": [], "scores": {"faithfulness": 99, "coverage": -4}})]
    )

    card = judge_run(
        _run(), _transcript(), scenario, JudgeSettings("judge-model"), client=client
    )

    assert card.rubric.faithfulness == 5.0
    assert card.rubric.coverage == 0.0
