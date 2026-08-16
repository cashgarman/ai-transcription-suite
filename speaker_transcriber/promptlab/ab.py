"""Blinded A/B comparisons and the standings they produce.

Two runs only belong in a pair when they summarized the same transcript, so the
only thing that differs is the prompt. Sides are shuffled per pair and the UI
keeps the variant names hidden until a vote is cast, because knowing which one
is the new candidate is enough to bias the vote.

The judge model gets scored too. `judge_agreement` measures how often it picked
the same winner the human did, which is the number that says whether the
automatic scores can be trusted to run ahead of a person.
"""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from dataclasses import dataclass

from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.promptlab.types import (
    ABPair,
    GROUNDED_MODE,
    HumanVerdict,
    SummaryRun,
    Scorecard,
    VariantStanding,
    WINNER_LEFT,
    WINNER_RIGHT,
    WINNER_TIE,
    new_id,
    normalize_tags,
)


LOGGER = logging.getLogger("speaker_transcriber.promptlab.ab")

ELO_START = 1500.0
ELO_K = 24.0


def _pair_key(pair: ABPair) -> tuple[str, frozenset[str]]:
    return (pair.transcript_id, frozenset((pair.left_run_id, pair.right_run_id)))


def build_pairs(
    store: LabStore,
    variant_a: str,
    variant_b: str,
    *,
    style_id: str = "",
    transcript_ids: tuple[str, ...] = (),
    seed: int | None = None,
) -> list[ABPair]:
    """One pair per transcript that both variants successfully summarized."""
    if variant_a == variant_b:
        raise ValueError("A comparison needs two different variants.")
    rng = random.Random(seed)
    wanted = set(transcript_ids) if transcript_ids else None

    runs: dict[str, dict[str, SummaryRun]] = defaultdict(dict)
    for run in store.runs.all():
        if not run.succeeded:
            continue
        if style_id and run.style_id != style_id:
            continue
        if wanted is not None and run.transcript_id not in wanted:
            continue
        if run.variant_id not in (variant_a, variant_b):
            continue
        # Keep the newest run per variant per transcript.
        existing = runs[run.transcript_id].get(run.variant_id)
        if existing is None or run.created_at >= existing.created_at:
            runs[run.transcript_id][run.variant_id] = run

    existing_keys = {_pair_key(pair) for pair in store.pairs.all()}
    created: list[ABPair] = []
    for transcript_id in sorted(runs):
        by_variant = runs[transcript_id]
        first = by_variant.get(variant_a)
        second = by_variant.get(variant_b)
        if first is None or second is None:
            continue
        if rng.random() < 0.5:
            first, second = second, first
        pair = ABPair(
            pair_id=new_id("pair"),
            transcript_id=transcript_id,
            style_id=first.style_id,
            left_run_id=first.run_id,
            right_run_id=second.run_id,
            left_variant_id=first.variant_id,
            right_variant_id=second.variant_id,
        )
        if _pair_key(pair) in existing_keys:
            continue
        store.pairs.save(pair)
        existing_keys.add(_pair_key(pair))
        created.append(pair)
    LOGGER.info("Built %d A/B pair(s) for %s vs %s", len(created), variant_a, variant_b)
    return created


def record_verdict(
    store: LabStore,
    pair_id: str,
    winner: str,
    *,
    tags: tuple[str, ...] = (),
    notes: str = "",
) -> HumanVerdict:
    if winner not in (WINNER_LEFT, WINNER_RIGHT, WINNER_TIE):
        raise ValueError(f"Unknown winner '{winner}'")
    if not store.pairs.exists(pair_id):
        raise KeyError(f"No A/B pair '{pair_id}'")
    verdict = HumanVerdict(
        pair_id=pair_id,
        winner=winner,
        tags=normalize_tags(tags),
        notes=str(notes).strip(),
    )
    store.verdicts.save(verdict)
    return verdict


@dataclass(frozen=True)
class DecidedPair:
    """A pair with its verdict resolved into variant ids."""

    pair: ABPair
    verdict: HumanVerdict
    winner_variant_id: str
    loser_variant_id: str

    @property
    def is_tie(self) -> bool:
        return self.verdict.winner == WINNER_TIE


def decided_pairs(store: LabStore, *, style_id: str = "") -> list[DecidedPair]:
    pairs = {pair.pair_id: pair for pair in store.pairs.all()}
    decided: list[DecidedPair] = []
    for verdict in store.verdicts.all():
        pair = pairs.get(verdict.pair_id)
        if pair is None:
            continue
        if style_id and pair.style_id != style_id:
            continue
        if verdict.winner == WINNER_TIE:
            decided.append(
                DecidedPair(pair, verdict, pair.left_variant_id, pair.right_variant_id)
            )
            continue
        winner = pair.variant_id_for(verdict.winner)
        loser = pair.variant_id_for(
            WINNER_RIGHT if verdict.winner == WINNER_LEFT else WINNER_LEFT
        )
        decided.append(DecidedPair(pair, verdict, winner, loser))
    decided.sort(key=lambda item: item.verdict.created_at)
    return decided


def _elo_update(rating_a: float, rating_b: float, score_a: float) -> tuple[float, float]:
    expected_a = 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))
    delta = ELO_K * (score_a - expected_a)
    return rating_a + delta, rating_b - delta


def elo_ratings(store: LabStore, *, style_id: str = "") -> dict[str, float]:
    """Elo per variant, replayed in the order the verdicts were cast."""
    ratings: dict[str, float] = defaultdict(lambda: ELO_START)
    for item in decided_pairs(store, style_id=style_id):
        first, second = item.winner_variant_id, item.loser_variant_id
        if first == second:
            continue
        score = 0.5 if item.is_tie else 1.0
        ratings[first], ratings[second] = _elo_update(ratings[first], ratings[second], score)
    return dict(ratings)


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def standings(store: LabStore, *, style_id: str = "", labels: dict[str, str] | None = None) -> list[VariantStanding]:
    """Every variant with runs or verdicts, ranked by Elo then composite score."""
    scores: dict[str, list[Scorecard]] = defaultdict(list)
    for scorecard in store.scores.all():
        if style_id and scorecard.style_id != style_id:
            continue
        scores[scorecard.variant_id].append(scorecard)

    runs_by_variant: dict[str, int] = defaultdict(int)
    for run in store.runs.all():
        if style_id and run.style_id != style_id:
            continue
        runs_by_variant[run.variant_id] += 1

    wins: dict[str, int] = defaultdict(int)
    losses: dict[str, int] = defaultdict(int)
    ties: dict[str, int] = defaultdict(int)
    for item in decided_pairs(store, style_id=style_id):
        if item.is_tie:
            ties[item.winner_variant_id] += 1
            ties[item.loser_variant_id] += 1
            continue
        wins[item.winner_variant_id] += 1
        losses[item.loser_variant_id] += 1

    ratings = elo_ratings(store, style_id=style_id)
    variant_ids = set(scores) | set(runs_by_variant) | set(ratings)

    table: list[VariantStanding] = []
    for variant_id in variant_ids:
        cards = [card for card in scores.get(variant_id, []) if not card.error]
        table.append(
            VariantStanding(
                variant_id=variant_id,
                label=(labels or {}).get(variant_id, variant_id),
                runs=runs_by_variant.get(variant_id, 0),
                wins=wins.get(variant_id, 0),
                losses=losses.get(variant_id, 0),
                ties=ties.get(variant_id, 0),
                elo=round(ratings.get(variant_id, ELO_START), 1),
                mean_composite=_mean([card.composite for card in cards]),
                mean_recall=_mean(
                    [card.recall for card in cards if card.mode == GROUNDED_MODE]
                ),
                mean_precision=_mean([card.precision for card in cards]),
                mean_rubric=_mean([card.rubric.mean for card in cards]),
            )
        )
    table.sort(key=lambda row: (row.elo, row.mean_composite), reverse=True)
    return table


@dataclass(frozen=True)
class JudgeAgreement:
    compared: int = 0
    agreed: int = 0
    disagreed: int = 0
    undecidable: int = 0

    @property
    def rate(self) -> float:
        return round(self.agreed / self.compared, 4) if self.compared else 0.0

    @property
    def summary(self) -> str:
        if not self.compared:
            return "No comparable verdicts yet."
        return (
            f"{self.agreed} of {self.compared} verdicts matched the judge "
            f"({self.rate * 100:.0f}%)."
        )


def judge_agreement(store: LabStore, *, style_id: str = "") -> JudgeAgreement:
    """How often the judge's composite picked the same winner the human did.

    Ties on either side are counted as undecidable rather than as agreement:
    crediting the judge for a coin flip would flatter it.
    """
    cards = {card.run_id: card for card in store.scores.all() if not card.error}
    agreed = disagreed = undecidable = 0
    for item in decided_pairs(store, style_id=style_id):
        left = cards.get(item.pair.left_run_id)
        right = cards.get(item.pair.right_run_id)
        if left is None or right is None or item.is_tie or left.composite == right.composite:
            undecidable += 1
            continue
        judge_pick = (
            item.pair.left_variant_id
            if left.composite > right.composite
            else item.pair.right_variant_id
        )
        if judge_pick == item.winner_variant_id:
            agreed += 1
        else:
            disagreed += 1
    return JudgeAgreement(
        compared=agreed + disagreed,
        agreed=agreed,
        disagreed=disagreed,
        undecidable=undecidable,
    )


def tag_tally(store: LabStore, variant_id: str, *, style_id: str = "") -> dict[str, int]:
    """How often each complaint tag was attached to a loss for one variant."""
    counts: dict[str, int] = defaultdict(int)
    for item in decided_pairs(store, style_id=style_id):
        if item.is_tie or item.loser_variant_id != variant_id:
            continue
        for tag in item.verdict.tags:
            counts[tag] += 1
    return dict(counts)
