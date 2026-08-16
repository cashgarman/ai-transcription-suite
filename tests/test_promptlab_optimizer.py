import json
import shutil

import pytest

from promptlab_fakes import FakeOllamaClient
from speaker_transcriber import prompts as prompt_registry
from speaker_transcriber.prompts import get_prompt, reload_prompts
from speaker_transcriber.promptlab.ab import record_verdict
from speaker_transcriber.promptlab.optimizer import (
    OptimizerSettings,
    build_evidence,
    candidate_diff,
    propose_prompt,
    save_candidate,
    stage_failure_hint,
)
from speaker_transcriber.promptlab.promptset import shipped_variant, stage_text
from speaker_transcriber.promptlab.scenarios import build_scenario
from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.promptlab.types import (
    ABPair,
    AUTHOR_OPTIMIZER,
    FactVerdict,
    RubricScores,
    STATUS_MISSING,
    Scorecard,
    StructureMetrics,
    SummaryRun,
    WINNER_LEFT,
)


STYLE = "meeting_summary"


@pytest.fixture
def isolated_prompts(tmp_path, monkeypatch):
    copy = tmp_path / "prompts"
    shutil.copytree(prompt_registry.prompts_dir(), copy)
    monkeypatch.setattr(prompt_registry, "prompts_dir", lambda: copy)
    reload_prompts()
    yield copy
    monkeypatch.undo()
    reload_prompts()


@pytest.fixture
def store(tmp_path):
    lab = LabStore(tmp_path / "lab")
    lab.ensure()
    return lab


@pytest.fixture
def graded(store):
    """A store holding one scenario, one run, and a scorecard full of failures."""
    scenario = build_scenario(51, kind_id="product_review", duration_minutes=45)
    store.scenarios.save(scenario)
    run = SummaryRun(
        run_id="run-1",
        transcript_id="txn-1",
        scenario_id=scenario.scenario_id,
        variant_id="shipped",
        variant_fingerprint="f",
        style_id=STYLE,
        model_name="m",
        num_ctx=8192,
        markdown="# Notes\n\nA thin summary.",
    )
    store.runs.save(run)
    store.scores.save(
        Scorecard(
            run_id="run-1",
            transcript_id="txn-1",
            variant_id="shipped",
            style_id=STYLE,
            mode="grounded",
            judge_model="judge",
            recall=0.4,
            precision=0.6,
            composite=0.45,
            rubric=RubricScores(3, 2, 4, 3, 4, 2),
            structure=StructureMetrics(
                expected_headings=("Action Items",),
                missing_headings=("Action Items",),
                action_table_required=True,
            ),
            fact_verdicts=tuple(
                FactVerdict(fact.fact_id, STATUS_MISSING) for fact in scenario.facts
            ),
            unsupported_claims=("Revenue tripled.",),
            asserted_distractors=("Hiring two contractors was approved.",),
        )
    )
    return store, scenario


def test_evidence_names_the_facts_that_were_dropped(graded):
    store, scenario = graded

    bundle = build_evidence(store, shipped_variant(STYLE), "chunk")

    assert bundle.runs_examined == 1
    assert bundle.missed_facts
    assert scenario.facts[0].text in "\n".join(bundle.missed_facts)


def test_evidence_quotes_unsupported_claims_and_distractors(graded):
    store, _ = graded

    bundle = build_evidence(store, shipped_variant(STYLE), "chunk")

    assert "Revenue tripled." in bundle.unsupported_claims
    assert any("abandoned idea" in claim for claim in bundle.unsupported_claims)


def test_evidence_reports_structural_failures(graded):
    store, _ = graded

    bundle = build_evidence(store, shipped_variant(STYLE), "merge")

    assert any("Action Items" in line for line in bundle.structure_failures)
    assert any("action table" in line for line in bundle.structure_failures)


def test_the_weakest_rubric_dimensions_are_surfaced(graded):
    store, _ = graded

    bundle = build_evidence(store, shipped_variant(STYLE), "chunk")

    assert bundle.weakest_dimensions
    assert "coverage" in " ".join(bundle.weakest_dimensions)


def test_thin_evidence_is_flagged_as_a_caveat(graded):
    store, _ = graded
    bundle = build_evidence(store, shipped_variant(STYLE), "chunk")
    assert any("weak" in warning for warning in bundle.warnings)


def test_an_empty_store_produces_an_empty_bundle(store):
    bundle = build_evidence(store, shipped_variant(STYLE), "chunk")
    assert bundle.is_empty
    assert bundle.runs_examined == 0


def test_human_notes_reach_the_bundle(graded):
    store, _ = graded
    store.runs.save(
        SummaryRun(
            run_id="run-2",
            transcript_id="txn-1",
            scenario_id="scn",
            variant_id="var-1",
            variant_fingerprint="g",
            style_id=STYLE,
            model_name="m",
            num_ctx=8192,
            markdown="# Better notes",
        )
    )
    store.pairs.save(ABPair("pair-1", "txn-1", STYLE, "run-2", "run-1", "var-1", "shipped"))
    record_verdict(
        store,
        "pair-1",
        WINNER_LEFT,
        tags=("missed_facts",),
        notes="Dropped the migration deadline entirely.",
    )

    bundle = build_evidence(store, shipped_variant(STYLE), "chunk")

    assert "Dropped the migration deadline entirely." in bundle.human_notes
    assert any("left out material" in line for line in bundle.complaint_tags)
    assert "0 wins, 1 losses" in bundle.head_to_head


def test_the_bundle_renders_as_readable_markdown(graded):
    store, _ = graded
    text = build_evidence(store, shipped_variant(STYLE), "chunk").to_markdown()

    assert "# Measured performance of this prompt" in text
    assert "# Facts the notes failed to carry" in text


def test_the_digest_changes_with_the_evidence(graded, tmp_path):
    graded_store, _ = graded
    blank = LabStore(tmp_path / "blank")
    blank.ensure()

    empty = build_evidence(blank, shipped_variant(STYLE), "chunk")
    full = build_evidence(graded_store, shipped_variant(STYLE), "chunk")

    assert empty.digest() != full.digest()


def test_the_stage_hint_routes_failures_to_a_stage(graded):
    store, _ = graded
    hints = stage_failure_hint(store, shipped_variant(STYLE))
    assert "chunk" in hints
    assert "merge" in hints


def test_an_unknown_stage_is_rejected(store):
    with pytest.raises(KeyError):
        build_evidence(store, shipped_variant(STYLE), "nonsense")


# Proposing


def _candidate_response(text="A rewritten chunk prompt that keeps every number."):
    return json.dumps({"prompt": text, "changelog": "Told it to keep figures."})


def test_a_candidate_is_produced_with_its_changelog(isolated_prompts, graded):
    store, _ = graded
    client = FakeOllamaClient([_candidate_response()])

    candidate = propose_prompt(
        store,
        shipped_variant(STYLE),
        "chunk",
        OptimizerSettings("opt-model"),
        client=client,
    )

    assert candidate.stage == "chunk"
    assert candidate.style_id == STYLE
    assert candidate.prompt_text.startswith("A rewritten chunk prompt")
    assert candidate.changelog == "Told it to keep figures."
    assert candidate.model_name == "opt-model"


def test_the_optimizer_sees_the_current_prompt_and_the_evidence(isolated_prompts, graded):
    store, scenario = graded
    client = FakeOllamaClient([_candidate_response()])

    propose_prompt(
        store,
        shipped_variant(STYLE),
        "chunk",
        OptimizerSettings("opt-model"),
        client=client,
    )

    prompt = client.prompts[0]
    assert get_prompt("chunk", STYLE)[:60] in prompt
    assert scenario.facts[0].text in prompt
    assert "Revenue tripled." in prompt


def test_unparseable_optimizer_output_is_an_error(isolated_prompts, graded):
    store, _ = graded
    client = FakeOllamaClient(["I would change the tone a bit."])

    with pytest.raises(RuntimeError, match="usable JSON"):
        propose_prompt(
            store, shipped_variant(STYLE), "chunk", OptimizerSettings("m"), client=client
        )


def test_an_empty_rewrite_is_an_error(isolated_prompts, graded):
    store, _ = graded
    client = FakeOllamaClient([json.dumps({"prompt": "   "})])

    with pytest.raises(RuntimeError, match="empty prompt"):
        propose_prompt(
            store, shipped_variant(STYLE), "chunk", OptimizerSettings("m"), client=client
        )


def test_an_unchanged_rewrite_is_an_error(isolated_prompts, graded):
    store, _ = graded
    client = FakeOllamaClient([json.dumps({"prompt": get_prompt("chunk", STYLE)})])

    with pytest.raises(RuntimeError, match="unchanged"):
        propose_prompt(
            store, shipped_variant(STYLE), "chunk", OptimizerSettings("m"), client=client
        )


def test_the_diff_shows_the_rewrite(isolated_prompts, graded):
    store, _ = graded
    client = FakeOllamaClient([_candidate_response()])
    base = shipped_variant(STYLE)
    candidate = propose_prompt(
        store, base, "chunk", OptimizerSettings("m"), client=client
    )

    diff = candidate_diff(store, candidate, base)

    assert "+A rewritten chunk prompt that keeps every number." in diff


def test_saving_a_candidate_files_it_as_a_variant(isolated_prompts, graded):
    store, _ = graded
    client = FakeOllamaClient([_candidate_response()])
    base = shipped_variant(STYLE)
    candidate = propose_prompt(
        store, base, "chunk", OptimizerSettings("m"), client=client
    )

    variant, recorded = save_candidate(store, candidate, base)

    assert variant.author == AUTHOR_OPTIMIZER
    assert variant.parent_id == base.variant_id
    assert stage_text(variant, "chunk") == candidate.prompt_text
    assert recorded.saved_variant_id == variant.variant_id
    assert store.candidates.require(candidate.candidate_id).saved_variant_id


def test_saving_never_touches_the_shipped_files(isolated_prompts, graded):
    store, _ = graded
    before = get_prompt("chunk", STYLE)
    client = FakeOllamaClient([_candidate_response()])
    base = shipped_variant(STYLE)
    candidate = propose_prompt(
        store, base, "chunk", OptimizerSettings("m"), client=client
    )

    save_candidate(store, candidate, base)

    assert get_prompt("chunk", STYLE) == before
