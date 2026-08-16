import pytest

from speaker_transcriber.promptlab.ab import (
    ELO_START,
    build_pairs,
    decided_pairs,
    elo_ratings,
    judge_agreement,
    record_verdict,
    standings,
    tag_tally,
)
from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.promptlab.types import (
    ABPair,
    RubricScores,
    Scorecard,
    SummaryRun,
    WINNER_LEFT,
    WINNER_RIGHT,
    WINNER_TIE,
)


STYLE = "meeting_summary"


@pytest.fixture
def store(tmp_path):
    lab = LabStore(tmp_path)
    lab.ensure()
    return lab


def _run(run_id, transcript_id, variant_id, markdown="# Notes\n\nBody.") -> SummaryRun:
    return SummaryRun(
        run_id=run_id,
        transcript_id=transcript_id,
        scenario_id="scn",
        variant_id=variant_id,
        variant_fingerprint="f",
        style_id=STYLE,
        model_name="m",
        num_ctx=8192,
        markdown=markdown,
    )


def _seed_runs(store, transcripts=("txn-1", "txn-2")):
    for index, transcript_id in enumerate(transcripts):
        store.runs.save(_run(f"a{index}", transcript_id, "shipped"))
        store.runs.save(_run(f"b{index}", transcript_id, "var-1"))


def test_pairs_are_built_per_shared_transcript(store):
    _seed_runs(store)

    pairs = build_pairs(store, "shipped", "var-1", style_id=STYLE)

    assert len(pairs) == 2
    for pair in pairs:
        assert {pair.left_variant_id, pair.right_variant_id} == {"shipped", "var-1"}
        assert pair.left_run_id != pair.right_run_id


def test_a_transcript_missing_one_side_is_skipped(store):
    store.runs.save(_run("a0", "txn-1", "shipped"))

    assert build_pairs(store, "shipped", "var-1", style_id=STYLE) == []


def test_failed_runs_are_never_paired(store):
    store.runs.save(_run("a0", "txn-1", "shipped"))
    store.runs.save(_run("b0", "txn-1", "var-1", markdown=""))

    assert build_pairs(store, "shipped", "var-1", style_id=STYLE) == []


def test_sides_are_shuffled_across_seeds(store):
    _seed_runs(store, [f"txn-{index}" for index in range(12)])

    pairs = build_pairs(store, "shipped", "var-1", style_id=STYLE, seed=1)
    left_variants = {pair.left_variant_id for pair in pairs}

    assert left_variants == {"shipped", "var-1"}


def test_rebuilding_does_not_duplicate_pairs(store):
    _seed_runs(store)
    build_pairs(store, "shipped", "var-1", style_id=STYLE)

    again = build_pairs(store, "shipped", "var-1", style_id=STYLE)

    assert again == []
    assert store.pairs.count() == 2


def test_a_variant_cannot_be_compared_with_itself(store):
    with pytest.raises(ValueError):
        build_pairs(store, "shipped", "shipped")


def test_recording_a_verdict_requires_a_real_pair(store):
    with pytest.raises(KeyError):
        record_verdict(store, "nope", WINNER_LEFT)


def test_an_unknown_winner_is_rejected(store):
    store.pairs.save(ABPair("pair-1", "txn-1", STYLE, "a0", "b0", "shipped", "var-1"))
    with pytest.raises(ValueError):
        record_verdict(store, "pair-1", "maybe")


def test_a_verdict_resolves_to_the_winning_variant(store):
    store.pairs.save(ABPair("pair-1", "txn-1", STYLE, "a0", "b0", "shipped", "var-1"))
    record_verdict(store, "pair-1", WINNER_RIGHT, tags=("too_long",), notes="Padded.")

    decided = decided_pairs(store)

    assert len(decided) == 1
    assert decided[0].winner_variant_id == "var-1"
    assert decided[0].loser_variant_id == "shipped"
    assert decided[0].verdict.tags == ("too_long",)


def test_winning_raises_elo_and_losing_lowers_it(store):
    store.pairs.save(ABPair("pair-1", "txn-1", STYLE, "a0", "b0", "shipped", "var-1"))
    record_verdict(store, "pair-1", WINNER_LEFT)

    ratings = elo_ratings(store)

    assert ratings["shipped"] > ELO_START
    assert ratings["var-1"] < ELO_START
    assert ratings["shipped"] + ratings["var-1"] == pytest.approx(2 * ELO_START)


def test_a_tie_between_equal_variants_moves_nothing(store):
    store.pairs.save(ABPair("pair-1", "txn-1", STYLE, "a0", "b0", "shipped", "var-1"))
    record_verdict(store, "pair-1", WINNER_TIE)

    ratings = elo_ratings(store)

    assert ratings["shipped"] == pytest.approx(ELO_START)
    assert ratings["var-1"] == pytest.approx(ELO_START)


def test_repeated_wins_keep_raising_elo_by_smaller_steps(store):
    for index in range(3):
        pair_id = f"pair-{index}"
        store.pairs.save(
            ABPair(pair_id, f"txn-{index}", STYLE, f"a{index}", f"b{index}", "shipped", "var-1")
        )
        record_verdict(store, pair_id, WINNER_LEFT)

    ratings = elo_ratings(store)

    assert ratings["shipped"] > ELO_START + 24
    assert ratings["shipped"] < ELO_START + 72


def test_standings_count_wins_losses_and_ties(store):
    for index, winner in enumerate((WINNER_LEFT, WINNER_RIGHT, WINNER_TIE)):
        pair_id = f"pair-{index}"
        store.pairs.save(
            ABPair(pair_id, f"txn-{index}", STYLE, f"a{index}", f"b{index}", "shipped", "var-1")
        )
        record_verdict(store, pair_id, winner)

    rows = {row.variant_id: row for row in standings(store, style_id=STYLE)}

    assert rows["shipped"].wins == 1
    assert rows["shipped"].losses == 1
    assert rows["shipped"].ties == 1
    assert rows["shipped"].win_rate == pytest.approx(0.5)
    assert rows["var-1"].win_rate == pytest.approx(0.5)


def test_win_rate_is_zero_before_any_comparison(store):
    _seed_runs(store, ["txn-1"])
    rows = {row.variant_id: row for row in standings(store, style_id=STYLE)}
    assert rows["shipped"].win_rate == 0.0
    assert rows["shipped"].runs == 1


def test_standings_average_the_scorecards(store):
    _seed_runs(store, ["txn-1"])
    store.scores.save(
        Scorecard(
            "a0", "txn-1", "shipped", STYLE, "grounded", "j",
            recall=0.8, precision=1.0, composite=0.9, rubric=RubricScores(4, 4, 4, 4, 4, 4),
        )
    )

    rows = {row.variant_id: row for row in standings(store, style_id=STYLE)}

    assert rows["shipped"].mean_composite == pytest.approx(0.9)
    assert rows["shipped"].mean_recall == pytest.approx(0.8)
    assert rows["shipped"].mean_rubric == pytest.approx(4.0)


def test_failed_scorecards_do_not_drag_the_averages(store):
    _seed_runs(store, ["txn-1"])
    store.scores.save(
        Scorecard("a0", "txn-1", "shipped", STYLE, "grounded", "j", composite=0.9)
    )
    store.scores.save(
        Scorecard("b0", "txn-1", "shipped", STYLE, "grounded", "j", error="broken")
    )

    rows = {row.variant_id: row for row in standings(store, style_id=STYLE)}
    assert rows["shipped"].mean_composite == pytest.approx(0.9)


def _agreement_case(store, human_winner, left_composite, right_composite):
    store.pairs.save(ABPair("pair-1", "txn-1", STYLE, "a0", "b0", "shipped", "var-1"))
    store.scores.save(
        Scorecard("a0", "txn-1", "shipped", STYLE, "grounded", "j", composite=left_composite)
    )
    store.scores.save(
        Scorecard("b0", "txn-1", "var-1", STYLE, "grounded", "j", composite=right_composite)
    )
    record_verdict(store, "pair-1", human_winner)
    return judge_agreement(store, style_id=STYLE)


def test_the_judge_agrees_when_it_picked_the_same_winner(store):
    agreement = _agreement_case(store, WINNER_LEFT, 0.9, 0.4)
    assert agreement.agreed == 1
    assert agreement.rate == 1.0


def test_the_judge_disagrees_when_it_picked_the_loser(store):
    agreement = _agreement_case(store, WINNER_RIGHT, 0.9, 0.4)
    assert agreement.disagreed == 1
    assert agreement.rate == 0.0


def test_a_human_tie_is_undecidable_rather_than_agreement(store):
    agreement = _agreement_case(store, WINNER_TIE, 0.9, 0.4)
    assert agreement.compared == 0
    assert agreement.undecidable == 1
    assert "No comparable verdicts" in agreement.summary


def test_equal_composites_are_undecidable(store):
    agreement = _agreement_case(store, WINNER_LEFT, 0.5, 0.5)
    assert agreement.undecidable == 1
    assert agreement.compared == 0


def test_unjudged_runs_are_undecidable(store):
    store.pairs.save(ABPair("pair-1", "txn-1", STYLE, "a0", "b0", "shipped", "var-1"))
    record_verdict(store, "pair-1", WINNER_LEFT)

    agreement = judge_agreement(store, style_id=STYLE)

    assert agreement.undecidable == 1


def test_tags_are_tallied_against_the_loser(store):
    store.pairs.save(ABPair("pair-1", "txn-1", STYLE, "a0", "b0", "shipped", "var-1"))
    record_verdict(store, "pair-1", WINNER_LEFT, tags=("missed_facts", "too_long"))

    assert tag_tally(store, "var-1") == {"missed_facts": 1, "too_long": 1}
    assert tag_tally(store, "shipped") == {}
