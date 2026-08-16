"""Versioned prompt variants for one summary style.

A variant stores only the stages it changes. Everything else resolves against
the shipped `.txt` files at call time, so a single-stage experiment does not
freeze stale copies of the other four stages and silently keep testing them
after the shipped prompts move on.

Promotion is the only operation that touches the files the app ships, and it
snapshots the current shipped text into the store first so the change is
reversible from inside the lab.
"""

from __future__ import annotations

import difflib
import logging

from speaker_transcriber.prompts import (
    PROMPT_FILENAMES,
    get_prompt,
    normalize_style,
    reload_prompts,
    style_dir,
    style_display_name,
)
from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.promptlab.types import (
    AUTHOR_HUMAN,
    AUTHOR_SHIPPED,
    PROMPT_STAGES,
    PromptVariant,
    SHIPPED_VARIANT_ID,
    fingerprint,
    new_id,
)


LOGGER = logging.getLogger("speaker_transcriber.promptlab.promptset")


def shipped_variant(style_id: str) -> PromptVariant:
    """The baseline every experiment is measured against."""
    style = normalize_style(style_id)
    return PromptVariant(
        variant_id=SHIPPED_VARIANT_ID,
        style_id=style,
        label=f"Shipped ({style_display_name(style)})",
        author=AUTHOR_SHIPPED,
        parent_id="",
        rationale="The prompt files the application currently ships.",
        stages={},
    )


def shipped_stages(style_id: str) -> dict[str, str]:
    style = normalize_style(style_id)
    return {stage: get_prompt(stage, style) for stage in PROMPT_STAGES}


def resolve_stages(variant: PromptVariant) -> dict[str, str]:
    """Every stage's effective text: the variant's override, else the shipped file."""
    resolved = shipped_stages(variant.style_id)
    for stage, text in variant.stages.items():
        if stage in resolved and str(text).strip():
            resolved[stage] = str(text)
    return resolved


def stage_text(variant: PromptVariant, stage: str) -> str:
    if stage not in PROMPT_STAGES:
        raise KeyError(f"Unknown prompt stage '{stage}'")
    override = variant.stages.get(stage, "")
    if override.strip():
        return override
    return get_prompt(stage, variant.style_id)


def variant_overrides(variant: PromptVariant) -> dict[str, str]:
    """Just the overrides, which is what the summarizer needs to be handed."""
    return {
        stage: text
        for stage, text in variant.stages.items()
        if stage in PROMPT_STAGES and str(text).strip()
    }


def variant_fingerprint(variant: PromptVariant) -> str:
    """A hash of the resolved prompts, so runs can be grouped by what they used."""
    return fingerprint(resolve_stages(variant))


def load_variant(store: LabStore, style_id: str, variant_id: str) -> PromptVariant:
    style = normalize_style(style_id)
    if variant_id == SHIPPED_VARIANT_ID:
        return shipped_variant(style)
    variant = store.get_variant(style, variant_id)
    if variant is None:
        raise KeyError(f"No prompt variant '{variant_id}' for style '{style}'")
    return variant


def list_variants(store: LabStore, style_id: str) -> list[PromptVariant]:
    """Shipped first, then saved variants oldest to newest."""
    style = normalize_style(style_id)
    saved = [
        variant
        for variant in store.list_variants(style)
        if variant.variant_id != SHIPPED_VARIANT_ID
    ]
    return [shipped_variant(style), *saved]


def create_variant(
    store: LabStore,
    style_id: str,
    stages: dict[str, str],
    *,
    label: str = "",
    author: str = AUTHOR_HUMAN,
    parent_id: str = SHIPPED_VARIANT_ID,
    rationale: str = "",
) -> PromptVariant:
    style = normalize_style(style_id)
    overrides = {
        stage: str(text)
        for stage, text in (stages or {}).items()
        if stage in PROMPT_STAGES and str(text).strip()
    }
    if not overrides:
        raise ValueError("A variant must override at least one prompt stage.")
    variant = PromptVariant(
        variant_id=new_id("var"),
        style_id=style,
        label=label or f"Variant of {parent_id}",
        author=author,
        parent_id=parent_id,
        rationale=rationale,
        stages=overrides,
    )
    store.save_variant(variant)
    LOGGER.info(
        "Saved prompt variant %s for %s overriding %s",
        variant.variant_id,
        style,
        ", ".join(variant.overridden_stages),
    )
    return variant


def clone_variant(
    store: LabStore,
    variant: PromptVariant,
    *,
    label: str = "",
) -> PromptVariant:
    """A copy that starts from the parent's fully resolved text."""
    return create_variant(
        store,
        variant.style_id,
        resolve_stages(variant) if variant.is_shipped else dict(variant.stages),
        label=label or f"Copy of {variant.label}",
        author=AUTHOR_HUMAN,
        parent_id=variant.variant_id,
        rationale=f"Cloned from {variant.variant_id}.",
    )


def update_variant_stage(
    store: LabStore,
    variant: PromptVariant,
    stage: str,
    text: str,
) -> PromptVariant:
    if variant.is_shipped:
        raise ValueError("The shipped variant is edited by promoting a candidate.")
    if stage not in PROMPT_STAGES:
        raise KeyError(f"Unknown prompt stage '{stage}'")
    stages = dict(variant.stages)
    body = str(text).strip()
    if body:
        stages[stage] = body
    else:
        stages.pop(stage, None)
    if not stages:
        raise ValueError("A variant must override at least one prompt stage.")
    updated = PromptVariant(
        variant_id=variant.variant_id,
        style_id=variant.style_id,
        label=variant.label,
        author=variant.author,
        parent_id=variant.parent_id,
        rationale=variant.rationale,
        stages=stages,
        created_at=variant.created_at,
    )
    store.save_variant(updated)
    return updated


def snapshot_shipped(store: LabStore, style_id: str, *, reason: str = "") -> PromptVariant:
    """Freeze the current shipped prompts as a variant, so a promote is undoable."""
    style = normalize_style(style_id)
    variant = PromptVariant(
        variant_id=new_id("bak"),
        style_id=style,
        label=f"Shipped backup ({style_display_name(style)})",
        author=AUTHOR_SHIPPED,
        parent_id=SHIPPED_VARIANT_ID,
        rationale=reason or "Snapshot taken before promoting a candidate.",
        stages=shipped_stages(style),
    )
    store.save_variant(variant)
    return variant


def promote_variant(
    store: LabStore,
    variant: PromptVariant,
    *,
    stages: tuple[str, ...] = (),
) -> PromptVariant:
    """Write a variant's prompts into the shipped files.

    Returns the backup variant holding the text that was overwritten.
    """
    if variant.is_shipped:
        raise ValueError("The shipped variant is already live.")
    chosen = tuple(stages) or variant.overridden_stages
    unknown = [stage for stage in chosen if stage not in PROMPT_STAGES]
    if unknown:
        raise KeyError(f"Unknown prompt stage(s): {', '.join(unknown)}")
    if not chosen:
        raise ValueError("This variant overrides no prompt stages.")

    backup = snapshot_shipped(
        store,
        variant.style_id,
        reason=f"Taken before promoting {variant.variant_id}.",
    )
    directory = style_dir(variant.style_id)
    directory.mkdir(parents=True, exist_ok=True)
    for stage in chosen:
        path = directory / PROMPT_FILENAMES[stage]
        path.write_text(stage_text(variant, stage).strip() + "\n", encoding="utf-8")
        LOGGER.info("Promoted %s/%s from variant %s", variant.style_id, stage, variant.variant_id)
    reload_prompts()
    return backup


def restore_variant(store: LabStore, backup: PromptVariant) -> None:
    """Write a backup variant's stages back over the shipped files."""
    directory = style_dir(backup.style_id)
    directory.mkdir(parents=True, exist_ok=True)
    for stage, text in backup.stages.items():
        if stage not in PROMPT_FILENAMES:
            continue
        (directory / PROMPT_FILENAMES[stage]).write_text(
            str(text).strip() + "\n", encoding="utf-8"
        )
    reload_prompts()


def stage_diff(current: str, proposed: str, *, label: str = "prompt") -> str:
    """A unified diff, or an empty string when the two are identical."""
    before = str(current).strip().splitlines()
    after = str(proposed).strip().splitlines()
    if before == after:
        return ""
    return "\n".join(
        difflib.unified_diff(
            before,
            after,
            fromfile=f"{label} (current)",
            tofile=f"{label} (proposed)",
            lineterm="",
        )
    )


def variant_diff(variant: PromptVariant, stage: str) -> str:
    """How one stage of a variant differs from what the app ships today."""
    return stage_diff(
        get_prompt(stage, variant.style_id),
        stage_text(variant, stage),
        label=f"{variant.style_id}/{stage}",
    )
