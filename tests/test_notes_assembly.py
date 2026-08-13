from speaker_transcriber.models.notes_assembly import (
    assemble_notes,
    build_body,
    fit_titles,
    recent_lines,
    topic_titles,
)


FRONT_MATTER = (
    "# Weekly Sync\n\n"
    "*One line summary.*\n\n"
    "**Participants:** Cash, GranSeba\n\n"
    "## Executive Summary\n\nShort overview.\n\n"
    "## Action Items\n\n"
    "| Owner | Action | Priority |\n| --- | --- | --- |\n"
    "| Cash | Clear the derived data cache before the next package | High |\n"
)


def test_echoed_markers_and_preambles_are_removed() -> None:
    body = build_body(
        "",
        [
            "**Meeting Notes**\n\n"
            "## Shader Compilation\n"
            "- Cash: the packaged build fails on the shader compile step.\n\n"
            "[MORE SEGMENTS FOLLOW]",
            "**Continuation Brief**\n\n"
            "## Packaging\n- GranSeba: packaging works from the editor.\n\n"
            "[END OF TRANSCRIPT]",
        ],
    )
    assert "MORE SEGMENTS FOLLOW" not in body
    assert "END OF TRANSCRIPT" not in body
    assert "Meeting Notes" not in body
    assert "Continuation Brief" not in body
    assert "## Shader Compilation" in body
    assert "## Packaging" in body


def test_participant_blocks_and_placeholders_are_removed() -> None:
    body = build_body(
        "",
        [
            "**Participants**\n- Cash\n- GranSeba\n\n"
            "**Decisions**\n- No explicit decisions were recorded.\n\n"
            "**Questions**\n- None raised in this segment.\n\n"
            "**Technical details**\n- None.\n\n"
            "## Build Setup\n- Cash: Visual Studio needed the 14.38 toolchain.",
        ],
    )
    assert "## Build Setup" in body
    assert "14.38" in body
    assert "Cash\n- GranSeba" not in body
    assert "No explicit decisions" not in body
    assert "None raised" not in body
    assert "Decisions" not in body
    assert "Technical Details" not in body


def test_placeholder_wording_that_carries_content_is_kept() -> None:
    body = build_body(
        "",
        [
            "## Ownership\n"
            "- No one owns the deployment script yet, so Cash will draft an owner "
            "list and circulate it before Friday's review meeting.",
        ],
    )
    assert "deployment script" in body
    assert "circulate it before Friday" in body


def test_same_topic_written_differently_becomes_one_section() -> None:
    body = build_body(
        "",
        [
            "## AI Tooling & Development Process\n- Cash: the analyzer writes docs.",
            "## AI Tooling and Development Process (Recap)\n"
            "- Cash: the analyzer also writes unit tests.",
            "## Continuation Discussion (AI Tooling and Development Process)\n"
            "- GranSeba: the graph view shows single-connection islands.",
        ],
    )
    assert body.count("## AI Tooling") == 1
    assert "Recap" not in body
    assert "Continuation" not in body
    for detail in ("writes docs", "writes unit tests", "single-connection islands"):
        assert detail in body


def test_a_topic_that_only_mentions_a_label_stays_a_topic() -> None:
    """"Project Status and Technical Details" is a topic, not the details bucket."""
    body = build_body(
        "",
        [
            "## Project Status and Technical Details\n- Cash: the build is 5.8.\n\n"
            "## Technical details\n- Unreal Engine 5.8, MSVC 14.38.",
        ],
    )
    assert "## Project Status and Technical Details" in body
    assert body.count("## Technical Details") == 1
    assert body.index("## Project Status") < body.index("## Technical Details")


def test_verbatim_and_labeled_recaps_are_dropped() -> None:
    first = "## Timeline\n- Cash: the replay system needs deterministic turn order."
    body = build_body(
        "",
        [
            first,
            "## Recap of Previous Discussion\n"
            "- Cash: the replay system needs deterministic turn order.\n"
            "- Cash: the editor build kept working.\n\n"
            "## Timeline\n"
            "- Cash: the replay system needs deterministic turn order.\n"
            "- GranSeba: UNIQUE_SEED the seed should be saved with each turn.",
        ],
    )
    assert body.count("deterministic turn order") == 1
    assert "Recap" not in body
    assert "editor build kept working" not in body
    assert "UNIQUE_SEED" in body


def test_lightly_reworded_repeats_are_dropped() -> None:
    body = build_body(
        "",
        [
            "## Determinism\n- Cash: the seed must be saved with every single turn.",
            "## Determinism\n"
            "- Cash: the seed must be saved with every turn.\n"
            "- Cash: UNIQUE_COSMETIC cosmetic rolls do not need a save state.",
        ],
    )
    assert body.count("the seed must be saved") == 1
    assert "UNIQUE_COSMETIC" in body


def test_distinct_lines_that_share_wording_are_both_kept() -> None:
    body = build_body(
        "",
        [
            "## Branches\n- Cash: the new timeline logic branch holds the phased plan.",
            "## Branches\n- Cash: the replay system branch holds the older prototype.",
        ],
    )
    assert "phased plan" in body
    assert "older prototype" in body


def test_category_items_the_overview_already_lists_are_folded_out() -> None:
    body = build_body(
        FRONT_MATTER,
        [
            "## Action items\n"
            "- Cash: clear the derived data cache before the next package.\n"
            "- GranSeba: UNIQUE_REVIEW review the ability tools branch this week.",
        ],
    )
    assert "clear the derived data cache" not in body
    assert "UNIQUE_REVIEW" in body
    assert "## Additional Action Items" in body


def test_a_fully_covered_category_section_disappears() -> None:
    body = build_body(
        FRONT_MATTER,
        ["## Action items\n- Cash: clear the derived data cache before the next package."],
    )
    assert body == ""


def test_wrapped_continuation_lines_follow_the_line_they_belong_to() -> None:
    bullet = (
        "- Cash: the packaged build fails on the shader compile step because the\n"
        "  derived data cache still holds 5.6 artifacts."
    )
    body = build_body("", [f"## Packaging\n{bullet}", f"## Packaging\n{bullet}"])
    assert body.count("derived data cache still holds") == 1
    assert "derived data cache still holds 5.6 artifacts." in body


def test_every_extract_contributes_its_unique_detail() -> None:
    letters = "ABCDEFGHIJKL"
    extracts = [
        f"## Feature Area {letter}\n"
        f"- Cash: UNIQUE_{letter} point {letter} was raised.\n\n"
        "**Participants**\n- Cash\n- GranSeba\n\n"
        "**Decisions**\n- None recorded in this segment.\n\n"
        "[MORE SEGMENTS FOLLOW]"
        for letter in letters
    ]
    body = build_body(FRONT_MATTER, extracts)
    for letter in letters:
        assert f"UNIQUE_{letter}" in body
        assert body.count(f"## Feature Area {letter}") == 1


def test_assemble_notes_keeps_the_overview_first() -> None:
    document = assemble_notes(FRONT_MATTER, ["## Packaging\n- Cash: shader step fails."])
    assert document.startswith("# Weekly Sync")
    assert document.index("## Executive Summary") < document.index("## Packaging")


def test_topic_titles_skips_scaffolding_headings() -> None:
    titles = topic_titles(
        [
            "**Participants**\n- Cash\n\n**Discussion**\n\n## Packaging\n- Cash: fails.",
            "## Packaging (Continued)\n- Cash: still fails.\n\n"
            "## Presentation Strategy\n- GranSeba: record the demo.\n\n"
            "**Action items**\n- Cash: clear the cache.",
        ]
    )
    assert titles == ["Packaging", "Presentation Strategy"]


def test_fit_titles_drops_the_oldest_titles_first() -> None:
    assert fit_titles(["Alpha", "Beta"], 100) == "Alpha; Beta"
    assert fit_titles(["Alpha", "Beta", "Gamma"], 12) == "…; Gamma"
    assert fit_titles([], 50) == ""


def test_recent_lines_returns_the_tail_within_budget() -> None:
    extract = (
        "**Participants**\n- Cash\n\n"
        "## Packaging\n- Cash: the shader step fails.\n\n"
        "## Wrap-up\n- Cash: regroup on Friday."
    )
    tail = recent_lines(extract, 60)
    assert "regroup on Friday" in tail
    assert "Participants" not in tail
    assert len(tail) <= 60
    assert recent_lines(extract, 0) == ""
