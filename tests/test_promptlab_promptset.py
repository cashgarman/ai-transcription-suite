import shutil

import pytest

from speaker_transcriber import prompts as prompt_registry
from speaker_transcriber.prompts import get_prompt, reload_prompts
from speaker_transcriber.promptlab.promptset import (
    clone_variant,
    create_variant,
    list_variants,
    load_variant,
    promote_variant,
    resolve_stages,
    restore_variant,
    shipped_variant,
    stage_diff,
    stage_text,
    update_variant_stage,
    variant_diff,
    variant_fingerprint,
    variant_overrides,
)
from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.promptlab.types import PROMPT_STAGES, SHIPPED_VARIANT_ID


STYLE = "meeting_summary"


@pytest.fixture
def isolated_prompts(tmp_path, monkeypatch):
    """A writable copy of the shipped prompt pack, so promoting is harmless."""
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


def test_shipped_variant_resolves_every_stage(isolated_prompts):
    variant = shipped_variant(STYLE)

    resolved = resolve_stages(variant)

    assert set(resolved) == set(PROMPT_STAGES)
    assert resolved["system"] == get_prompt("system", STYLE)
    assert variant.overridden_stages == ()
    assert variant_overrides(variant) == {}


def test_a_variant_only_overrides_the_stage_it_changes(isolated_prompts, store):
    variant = create_variant(store, STYLE, {"chunk": "New chunk instructions."})

    assert variant.overridden_stages == ("chunk",)
    assert variant_overrides(variant) == {"chunk": "New chunk instructions."}
    resolved = resolve_stages(variant)
    assert resolved["chunk"] == "New chunk instructions."
    assert resolved["merge"] == get_prompt("merge", STYLE)


def test_unoverridden_stages_track_the_shipped_files(isolated_prompts, store):
    variant = create_variant(store, STYLE, {"chunk": "Only the chunk changes."})
    (isolated_prompts / "styles" / STYLE / "merge.txt").write_text(
        "A brand new merge prompt.", encoding="utf-8"
    )
    reload_prompts()

    assert resolve_stages(variant)["merge"] == "A brand new merge prompt."


def test_a_variant_must_change_something(isolated_prompts, store):
    with pytest.raises(ValueError):
        create_variant(store, STYLE, {})


def test_fingerprint_changes_with_the_text(isolated_prompts, store):
    base = shipped_variant(STYLE)
    changed = create_variant(store, STYLE, {"system": "Different system prompt."})

    assert variant_fingerprint(base) != variant_fingerprint(changed)
    assert variant_fingerprint(base) == variant_fingerprint(shipped_variant(STYLE))


def test_variants_round_trip_through_the_store(isolated_prompts, store):
    created = create_variant(
        store, STYLE, {"validate": "Check harder."}, label="Stricter validation"
    )

    loaded = load_variant(store, STYLE, created.variant_id)

    assert loaded.label == "Stricter validation"
    assert loaded.stages == {"validate": "Check harder."}


def test_listing_puts_shipped_first(isolated_prompts, store):
    create_variant(store, STYLE, {"chunk": "One."})
    create_variant(store, STYLE, {"chunk": "Two."})

    listed = list_variants(store, STYLE)

    assert listed[0].variant_id == SHIPPED_VARIANT_ID
    assert len(listed) == 3


def test_cloning_shipped_freezes_the_current_text(isolated_prompts, store):
    clone = clone_variant(store, shipped_variant(STYLE), label="Frozen copy")

    assert set(clone.overridden_stages) == set(PROMPT_STAGES)
    assert clone.stages["system"] == get_prompt("system", STYLE)
    assert clone.parent_id == SHIPPED_VARIANT_ID


def test_updating_a_stage_persists(isolated_prompts, store):
    variant = create_variant(store, STYLE, {"chunk": "First."})

    updated = update_variant_stage(store, variant, "merge", "Second.")

    assert set(updated.overridden_stages) == {"chunk", "merge"}
    assert load_variant(store, STYLE, variant.variant_id).stages["merge"] == "Second."


def test_clearing_a_stage_falls_back_to_shipped(isolated_prompts, store):
    variant = create_variant(store, STYLE, {"chunk": "First.", "merge": "Second."})

    updated = update_variant_stage(store, variant, "merge", "")

    assert updated.overridden_stages == ("chunk",)
    assert stage_text(updated, "merge") == get_prompt("merge", STYLE)


def test_the_shipped_variant_cannot_be_edited(isolated_prompts, store):
    with pytest.raises(ValueError):
        update_variant_stage(store, shipped_variant(STYLE), "chunk", "nope")


def test_promoting_writes_the_shipped_file_and_reloads(isolated_prompts, store):
    variant = create_variant(store, STYLE, {"chunk": "Promoted chunk prompt."})

    backup = promote_variant(store, variant)

    assert get_prompt("chunk", STYLE) == "Promoted chunk prompt."
    path = isolated_prompts / "styles" / STYLE / "chunk.txt"
    assert path.read_text(encoding="utf-8").strip() == "Promoted chunk prompt."
    assert backup.stages["chunk"] != "Promoted chunk prompt."


def test_promoting_leaves_other_stages_alone(isolated_prompts, store):
    before = get_prompt("merge", STYLE)
    variant = create_variant(store, STYLE, {"chunk": "Only chunk."})

    promote_variant(store, variant)

    assert get_prompt("merge", STYLE) == before


def test_a_backup_restores_the_previous_text(isolated_prompts, store):
    original = get_prompt("chunk", STYLE)
    variant = create_variant(store, STYLE, {"chunk": "Replacement."})
    backup = promote_variant(store, variant)

    restore_variant(store, backup)

    assert get_prompt("chunk", STYLE) == original


def test_the_shipped_variant_cannot_be_promoted(isolated_prompts, store):
    with pytest.raises(ValueError):
        promote_variant(store, shipped_variant(STYLE))


def test_diff_is_empty_when_nothing_changed(isolated_prompts, store):
    assert stage_diff("same text", "same text") == ""
    assert variant_diff(shipped_variant(STYLE), "chunk") == ""


def test_diff_reports_the_change(isolated_prompts, store):
    variant = create_variant(store, STYLE, {"chunk": "A completely new chunk prompt."})

    diff = variant_diff(variant, "chunk")

    assert "+A completely new chunk prompt." in diff
    assert "meeting_summary/chunk" in diff
