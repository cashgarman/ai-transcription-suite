"""On-disk store for everything the Prompt Lab produces.

Plain JSON files under the app data directory, one file per record. Volumes are
small (hundreds of records), so listing reads the directory rather than keeping
an index that could drift out of sync with the files.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Generic, TypeVar

from speaker_transcriber.config import app_data_dir
from speaker_transcriber.promptlab.types import (
    ABPair,
    GeneratedTranscript,
    HumanVerdict,
    OptimizerCandidate,
    PromptVariant,
    Scenario,
    Scorecard,
    SummaryRun,
)


LOGGER = logging.getLogger("speaker_transcriber.promptlab.store")

T = TypeVar("T")


def _safe_name(identifier: str) -> str:
    """A filename-safe form of an id, so a bad id cannot escape its folder."""
    cleaned = "".join(
        char if char.isalnum() or char in "-_." else "_" for char in str(identifier)
    ).strip("._")
    if not cleaned:
        raise ValueError("Record id is empty.")
    return cleaned


def write_json(path: Path, payload: Any) -> None:
    """Write atomically so a crash mid-write cannot leave a truncated record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        LOGGER.warning("Skipping unreadable Prompt Lab record: %s", path)
        return None


class JsonCollection(Generic[T]):
    """One folder of JSON records addressed by id."""

    def __init__(
        self,
        directory: Path,
        parse: Callable[[dict[str, Any]], T],
        identify: Callable[[T], str],
        sort_key: Callable[[T], Any] | None = None,
    ) -> None:
        self.directory = directory
        self._parse = parse
        self._identify = identify
        self._sort_key = sort_key

    def path_for(self, identifier: str) -> Path:
        return self.directory / f"{_safe_name(identifier)}.json"

    def save(self, record: T) -> T:
        write_json(self.path_for(self._identify(record)), record.to_dict())  # type: ignore[attr-defined]
        return record

    def save_all(self, records: Iterable[T]) -> None:
        for record in records:
            self.save(record)

    def get(self, identifier: str) -> T | None:
        path = self.path_for(identifier)
        if not path.is_file():
            return None
        data = read_json(path)
        return None if data is None else self._parse(data)

    def require(self, identifier: str) -> T:
        record = self.get(identifier)
        if record is None:
            raise KeyError(f"No record '{identifier}' in {self.directory.name}")
        return record

    def exists(self, identifier: str) -> bool:
        return self.path_for(identifier).is_file()

    def delete(self, identifier: str) -> None:
        self.path_for(identifier).unlink(missing_ok=True)

    def all(self) -> list[T]:
        if not self.directory.is_dir():
            return []
        records: list[T] = []
        for path in sorted(self.directory.glob("*.json")):
            data = read_json(path)
            if data is None:
                continue
            try:
                records.append(self._parse(data))
            except Exception:
                LOGGER.warning("Skipping malformed record: %s", path, exc_info=True)
        if self._sort_key is not None:
            records.sort(key=self._sort_key)
        return records

    def count(self) -> int:
        if not self.directory.is_dir():
            return 0
        return sum(1 for _ in self.directory.glob("*.json"))


def _newest_first(record: Any) -> Any:
    return (str(getattr(record, "created_at", "")),)


class LabStore:
    """Every Prompt Lab collection, rooted at one directory."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else app_data_dir() / "promptlab"
        self.scenarios: JsonCollection[Scenario] = JsonCollection(
            self.root / "scenarios",
            Scenario.from_dict,
            lambda record: record.scenario_id,
            _newest_first,
        )
        self.transcripts: JsonCollection[GeneratedTranscript] = JsonCollection(
            self.root / "transcripts",
            GeneratedTranscript.from_dict,
            lambda record: record.transcript_id,
            _newest_first,
        )
        self.runs: JsonCollection[SummaryRun] = JsonCollection(
            self.root / "runs",
            SummaryRun.from_dict,
            lambda record: record.run_id,
            _newest_first,
        )
        self.scores: JsonCollection[Scorecard] = JsonCollection(
            self.root / "scores",
            Scorecard.from_dict,
            lambda record: record.run_id,
            _newest_first,
        )
        self.pairs: JsonCollection[ABPair] = JsonCollection(
            self.root / "pairs",
            ABPair.from_dict,
            lambda record: record.pair_id,
            _newest_first,
        )
        self.verdicts: JsonCollection[HumanVerdict] = JsonCollection(
            self.root / "verdicts",
            HumanVerdict.from_dict,
            lambda record: record.pair_id,
            _newest_first,
        )
        self.candidates: JsonCollection[OptimizerCandidate] = JsonCollection(
            self.root / "candidates",
            OptimizerCandidate.from_dict,
            lambda record: record.candidate_id,
            _newest_first,
        )

    def ensure(self) -> None:
        for directory in (
            self.scenarios.directory,
            self.transcripts.directory,
            self.runs.directory,
            self.scores.directory,
            self.pairs.directory,
            self.verdicts.directory,
            self.candidates.directory,
            self.variants_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    # Variants are filed per style so a style's history stays browsable on disk.

    @property
    def variants_dir(self) -> Path:
        return self.root / "variants"

    def variant_path(self, style_id: str, variant_id: str) -> Path:
        return self.variants_dir / _safe_name(style_id) / f"{_safe_name(variant_id)}.json"

    def save_variant(self, variant: PromptVariant) -> PromptVariant:
        write_json(
            self.variant_path(variant.style_id, variant.variant_id),
            variant.to_dict(),
        )
        return variant

    def get_variant(self, style_id: str, variant_id: str) -> PromptVariant | None:
        path = self.variant_path(style_id, variant_id)
        if not path.is_file():
            return None
        data = read_json(path)
        return None if data is None else PromptVariant.from_dict(data)

    def delete_variant(self, style_id: str, variant_id: str) -> None:
        self.variant_path(style_id, variant_id).unlink(missing_ok=True)

    def list_variants(self, style_id: str) -> list[PromptVariant]:
        directory = self.variants_dir / _safe_name(style_id)
        if not directory.is_dir():
            return []
        variants: list[PromptVariant] = []
        for path in sorted(directory.glob("*.json")):
            data = read_json(path)
            if data is None:
                continue
            variants.append(PromptVariant.from_dict(data))
        variants.sort(key=lambda variant: variant.created_at)
        return variants

    # Convenience queries the UI leans on.

    def runs_for_transcript(self, transcript_id: str) -> list[SummaryRun]:
        return [run for run in self.runs.all() if run.transcript_id == transcript_id]

    def runs_for_variant(self, variant_id: str) -> list[SummaryRun]:
        return [run for run in self.runs.all() if run.variant_id == variant_id]

    def transcripts_for_style(self, style_id: str) -> list[GeneratedTranscript]:
        return [
            transcript
            for transcript in self.transcripts.all()
            if transcript.style_id == style_id
        ]

    def unjudged_runs(self) -> list[SummaryRun]:
        judged = {score.run_id for score in self.scores.all()}
        return [run for run in self.runs.all() if run.run_id not in judged]

    def unvoted_pairs(self) -> list[ABPair]:
        voted = {verdict.pair_id for verdict in self.verdicts.all()}
        return [pair for pair in self.pairs.all() if pair.pair_id not in voted]
