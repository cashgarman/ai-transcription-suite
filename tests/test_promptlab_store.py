import json

import pytest

from speaker_transcriber.promptlab.scenarios import build_scenario, scenario_content_key
from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.promptlab.types import (
    ABPair,
    FactVerdict,
    GeneratedTranscript,
    HumanVerdict,
    OptimizerCandidate,
    PromptVariant,
    RubricScores,
    STATUS_COVERED,
    Scorecard,
    StructureMetrics,
    SummaryRun,
    WINNER_LEFT,
    new_id,
    normalize_tags,
)


@pytest.fixture
def store(tmp_path):
    lab = LabStore(tmp_path)
    lab.ensure()
    return lab


def _transcript(transcript_id="txn-1", **overrides) -> GeneratedTranscript:
    fields = {
        "transcript_id": transcript_id,
        "scenario_id": "scn-1",
        "seed": 3,
        "mode": "grounded",
        "style_id": "meeting_summary",
        "label": "A meeting",
        "generator_model": "gen",
        "generator_num_ctx": 8192,
        "duration_seconds": 90.0,
        "word_count": 250,
        "transcript": {"source_file": "a.wav"},
    }
    fields.update(overrides)
    return GeneratedTranscript(**fields)


def _run(run_id="run-1", **overrides) -> SummaryRun:
    fields = {
        "run_id": run_id,
        "transcript_id": "txn-1",
        "scenario_id": "scn-1",
        "variant_id": "shipped",
        "variant_fingerprint": "f",
        "style_id": "meeting_summary",
        "model_name": "m",
        "num_ctx": 8192,
        "markdown": "# Notes",
    }
    fields.update(overrides)
    return SummaryRun(**fields)


def test_scenarios_round_trip(store):
    scenario = build_scenario(77, kind_id="architecture_review", duration_minutes=45)

    store.scenarios.save(scenario)
    loaded = store.scenarios.require(scenario.scenario_id)

    assert scenario_content_key(loaded) == scenario_content_key(scenario)
    assert loaded.facts[0].salience == scenario.facts[0].salience
    assert loaded.distractors == scenario.distractors


def test_transcripts_round_trip_with_their_payload(store):
    transcript = _transcript(transcript={"source_file": "a.wav", "segments": []})

    store.transcripts.save(transcript)
    loaded = store.transcripts.require("txn-1")

    assert loaded.transcript["source_file"] == "a.wav"
    assert loaded.word_count == 250


def test_scorecards_round_trip_including_nested_records(store):
    card = Scorecard(
        run_id="run-1",
        transcript_id="txn-1",
        variant_id="shipped",
        style_id="meeting_summary",
        mode="grounded",
        judge_model="judge",
        recall=0.75,
        precision=0.9,
        composite=0.8,
        rubric=RubricScores(4, 3, 5, 4, 3, 4),
        structure=StructureMetrics(expected_headings=("A",), missing_headings=("A",)),
        fact_verdicts=(FactVerdict("T1-DEC1", STATUS_COVERED, "quote"),),
        unsupported_claims=("nope",),
    )

    store.scores.save(card)
    loaded = store.scores.require("run-1")

    assert loaded.rubric.mean == card.rubric.mean
    assert loaded.structure.missing_headings == ("A",)
    assert loaded.fact_verdicts[0].evidence == "quote"
    assert loaded.unsupported_claims == ("nope",)


def test_a_scorecard_is_keyed_by_its_run(store):
    store.scores.save(Scorecard("run-1", "txn-1", "v", "s", "grounded", "j", recall=0.1))
    store.scores.save(Scorecard("run-1", "txn-1", "v", "s", "grounded", "j", recall=0.9))

    assert store.scores.count() == 1
    assert store.scores.require("run-1").recall == 0.9


def test_missing_records_return_none_and_require_raises(store):
    assert store.runs.get("nope") is None
    with pytest.raises(KeyError):
        store.runs.require("nope")


def test_deleting_is_idempotent(store):
    store.runs.save(_run())
    store.runs.delete("run-1")
    store.runs.delete("run-1")
    assert store.runs.count() == 0


def test_a_corrupt_file_is_skipped_rather_than_crashing(store):
    store.runs.save(_run())
    (store.runs.directory / "broken.json").write_text("{not json", encoding="utf-8")

    assert len(store.runs.all()) == 1


def test_ids_are_sanitized_into_filenames(store):
    store.runs.save(_run(run_id="../escape"))
    assert not (store.root.parent / "escape.json").exists()
    assert store.runs.count() == 1


def test_an_empty_id_is_rejected(store):
    with pytest.raises(ValueError):
        store.runs.save(_run(run_id=""))


def test_writes_are_atomic_and_leave_no_temp_files(store):
    store.runs.save(_run())
    assert [path.name for path in store.runs.directory.iterdir()] == ["run-1.json"]


def test_variants_are_filed_per_style(store):
    first = PromptVariant("var-1", "meeting_summary", "A", stages={"chunk": "x"})
    second = PromptVariant("var-2", "technical_meeting", "B", stages={"chunk": "y"})
    store.save_variant(first)
    store.save_variant(second)

    assert [v.variant_id for v in store.list_variants("meeting_summary")] == ["var-1"]
    assert [v.variant_id for v in store.list_variants("technical_meeting")] == ["var-2"]
    assert store.get_variant("meeting_summary", "var-2") is None


def test_variant_stages_are_filtered_to_known_names(store):
    store.save_variant(
        PromptVariant("var-3", "meeting_summary", "C", stages={"chunk": "x", "bogus": "y"})
    )
    loaded = store.get_variant("meeting_summary", "var-3")
    assert loaded.stages == {"chunk": "x"}


def test_unjudged_runs_excludes_scored_ones(store):
    store.runs.save(_run("run-1"))
    store.runs.save(_run("run-2"))
    store.scores.save(Scorecard("run-1", "txn-1", "v", "s", "grounded", "j"))

    assert [run.run_id for run in store.unjudged_runs()] == ["run-2"]


def test_unvoted_pairs_excludes_decided_ones(store):
    store.pairs.save(ABPair("pair-1", "txn-1", "s", "run-1", "run-2", "a", "b"))
    store.pairs.save(ABPair("pair-2", "txn-1", "s", "run-3", "run-4", "a", "b"))
    store.verdicts.save(HumanVerdict("pair-1", WINNER_LEFT))

    assert [pair.pair_id for pair in store.unvoted_pairs()] == ["pair-2"]


def test_runs_can_be_queried_by_transcript_and_variant(store):
    store.runs.save(_run("run-1", transcript_id="txn-1", variant_id="shipped"))
    store.runs.save(_run("run-2", transcript_id="txn-2", variant_id="var-9"))

    assert [r.run_id for r in store.runs_for_transcript("txn-1")] == ["run-1"]
    assert [r.run_id for r in store.runs_for_variant("var-9")] == ["run-2"]


def test_candidates_round_trip(store):
    candidate = OptimizerCandidate(
        candidate_id=new_id("cand"),
        style_id="meeting_summary",
        stage="chunk",
        base_variant_id="shipped",
        prompt_text="Better chunk prompt.",
        changelog="Told it to keep the numbers.",
    )
    store.candidates.save(candidate)

    loaded = store.candidates.require(candidate.candidate_id)
    assert loaded.prompt_text == "Better chunk prompt."
    assert loaded.stage == "chunk"


def test_records_are_written_as_readable_json(store):
    store.runs.save(_run())
    payload = json.loads((store.runs.directory / "run-1.json").read_text(encoding="utf-8"))
    assert payload["style_id"] == "meeting_summary"


def test_unknown_verdict_tags_are_dropped():
    assert normalize_tags(("hallucinated", "not_a_tag")) == ("hallucinated",)
    assert normalize_tags(()) == ()
