import pytest

from promptlab_fakes import FakeOllamaClient, fake_summarizer_factory
from speaker_transcriber.promptlab.generator import (
    GenerationSettings,
    generate_transcript,
    summary_source_for,
)
from speaker_transcriber.promptlab.promptset import shipped_variant, variant_fingerprint
from speaker_transcriber.promptlab.scenarios import build_freeform_scenario, build_scenario
from speaker_transcriber.promptlab.summarize_runner import RunSettings, run_summary
from speaker_transcriber.promptlab.types import FREEFORM_MODE, GROUNDED_MODE


STYLE = "meeting_summary"


def _dialogue(scenario) -> str:
    return "\n".join(
        f"{person.name}: This is what {person.name} had to say about the topic at hand."
        for person in scenario.participants
    )


def _client(scenario) -> FakeOllamaClient:
    return FakeOllamaClient(lambda kwargs: _dialogue(scenario))


def test_generation_makes_one_call_per_topic():
    scenario = build_scenario(31, kind_id="product_review", duration_minutes=60)
    client = _client(scenario)

    generate_transcript(
        scenario, GenerationSettings("gen-model", num_ctx=8192), client=client
    )

    assert len(client.calls) == len(scenario.topics)


def test_each_topic_prompt_carries_only_its_own_facts():
    scenario = build_scenario(32, kind_id="architecture_review", duration_minutes=60)
    client = _client(scenario)

    generate_transcript(
        scenario, GenerationSettings("gen-model", num_ctx=8192), client=client
    )

    for index, topic in enumerate(scenario.topics):
        prompt = client.prompts[index]
        for fact in scenario.facts_for_topic(topic.topic_id):
            assert fact.text in prompt
        for other in scenario.topics:
            if other.topic_id == topic.topic_id:
                continue
            for fact in scenario.facts_for_topic(other.topic_id):
                assert fact.text not in prompt


def test_distractors_are_asked_for_separately():
    scenario = build_scenario(33, kind_id="product_review", duration_minutes=60)
    with_distractors = [
        topic for topic in scenario.topics if scenario.distractors_for_topic(topic.topic_id)
    ]
    if not with_distractors:
        pytest.skip("This seed planted no distractors.")
    client = _client(scenario)

    generate_transcript(
        scenario, GenerationSettings("gen-model", num_ctx=8192), client=client
    )

    index = scenario.topics.index(with_distractors[0])
    assert "Raised and dropped" in client.prompts[index]


def test_grounded_and_freeform_use_different_system_prompts():
    grounded = build_scenario(34, kind_id="team_sync", duration_minutes=20)
    freeform = build_freeform_scenario(34, kind_id="team_sync", duration_minutes=20)
    settings = GenerationSettings("gen-model", num_ctx=8192)

    grounded_client = _client(grounded)
    freeform_client = _client(freeform)
    generate_transcript(grounded, settings, client=grounded_client)
    generate_transcript(freeform, settings, client=freeform_client)

    assert grounded_client.systems[0] != freeform_client.systems[0]
    assert "Must be established" not in freeform_client.prompts[0]


def test_the_generated_transcript_records_its_provenance():
    scenario = build_scenario(35, kind_id="standup", duration_minutes=15)
    client = _client(scenario)

    transcript = generate_transcript(
        scenario, GenerationSettings("gen-model", num_ctx=16384), client=client
    )

    assert transcript.scenario_id == scenario.scenario_id
    assert transcript.seed == scenario.seed
    assert transcript.mode == GROUNDED_MODE
    assert transcript.style_id == scenario.style_id
    assert transcript.generator_model == "gen-model"
    assert transcript.generator_num_ctx == 16384
    assert transcript.word_count > 0
    assert transcript.duration_seconds > 0


def test_freeform_transcripts_are_marked_as_such():
    scenario = build_freeform_scenario(36, kind_id="design_critique")
    transcript = generate_transcript(
        scenario, GenerationSettings("gen-model"), client=_client(scenario)
    )
    assert transcript.mode == FREEFORM_MODE


def test_progress_runs_from_start_to_finish():
    scenario = build_scenario(37, kind_id="standup", duration_minutes=15)
    seen: list[float] = []

    generate_transcript(
        scenario,
        GenerationSettings("gen-model"),
        on_progress=lambda fraction, message: seen.append(fraction),
        client=_client(scenario),
    )

    assert seen[0] == 0.0
    assert seen[-1] == 1.0
    assert seen == sorted(seen)


def test_unusable_generator_output_fails_loudly():
    scenario = build_scenario(38, kind_id="standup", duration_minutes=15)
    client = FakeOllamaClient(lambda kwargs: "I am afraid I cannot do that.")

    with pytest.raises(RuntimeError, match="no usable dialogue"):
        generate_transcript(scenario, GenerationSettings("gen-model"), client=client)


def test_a_scenario_without_topics_is_rejected():
    scenario = build_scenario(39, kind_id="standup")
    empty = type(scenario)(**{**scenario.to_dict(), "topics": (), "participants": (), "facts": (), "distractors": ()})
    with pytest.raises(ValueError):
        generate_transcript(empty, GenerationSettings("gen-model"))


def test_summary_source_reads_like_a_transcript():
    scenario = build_scenario(40, kind_id="team_sync", duration_minutes=20)
    transcript = generate_transcript(
        scenario, GenerationSettings("gen-model"), client=_client(scenario)
    )

    source = summary_source_for(transcript)

    assert scenario.participants[0].name in source
    assert len(source.split()) > 20


# The runner


def _transcript(seed: int = 41):
    scenario = build_scenario(seed, kind_id="team_sync", duration_minutes=20)
    return scenario, generate_transcript(
        scenario, GenerationSettings("gen-model"), client=_client(scenario)
    )


def test_a_run_records_the_markdown_and_its_provenance():
    scenario, transcript = _transcript()
    variant = shipped_variant(transcript.style_id)

    run = run_summary(
        transcript,
        variant,
        RunSettings("sum-model", 8192),
        summarizer_factory=fake_summarizer_factory("# Notes\n\nAll good."),
    )

    assert run.markdown == "# Notes\n\nAll good."
    assert run.succeeded
    assert run.transcript_id == transcript.transcript_id
    assert run.scenario_id == scenario.scenario_id
    assert run.variant_id == variant.variant_id
    assert run.variant_fingerprint == variant_fingerprint(variant)
    assert run.model_name == "sum-model"
    assert run.num_ctx == 8192
    assert run.elapsed_seconds >= 0


def test_the_variant_overrides_reach_the_summarizer(tmp_path):
    from speaker_transcriber.promptlab.promptset import create_variant
    from speaker_transcriber.promptlab.store import LabStore

    store = LabStore(tmp_path)
    store.ensure()
    _, transcript = _transcript(42)
    variant = create_variant(
        store, transcript.style_id, {"chunk": "A very different chunk prompt."}
    )

    captured: dict = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return fake_summarizer_factory()(**kwargs)

    run_summary(
        transcript, variant, RunSettings("sum-model", 8192), summarizer_factory=factory
    )

    assert captured["prompt_overrides"] == {"chunk": "A very different chunk prompt."}
    assert captured["style"] == transcript.style_id


def test_the_summarizer_is_handed_the_rendered_transcript():
    _, transcript = _transcript(43)
    made: list = []

    def factory(**kwargs):
        summarizer = fake_summarizer_factory()(**kwargs)
        made.append(summarizer)
        return summarizer

    run_summary(
        transcript,
        shipped_variant(transcript.style_id),
        RunSettings("sum-model", 8192),
        summarizer_factory=factory,
    )

    assert made[0].source == summary_source_for(transcript)


def test_a_failing_summarizer_still_produces_a_record():
    _, transcript = _transcript(44)

    class Exploding:
        def summarize(self, *args, **kwargs):
            raise RuntimeError("the model fell over")

    run = run_summary(
        transcript,
        shipped_variant(transcript.style_id),
        RunSettings("sum-model", 8192),
        summarizer_factory=lambda **kwargs: Exploding(),
    )

    assert not run.succeeded
    assert run.error == "the model fell over"
    assert run.markdown == ""


def test_cancellation_is_not_swallowed():
    from speaker_transcriber.errors import ProcessingCancelled

    _, transcript = _transcript(45)

    class Cancelling:
        def summarize(self, *args, **kwargs):
            raise ProcessingCancelled()

    with pytest.raises(ProcessingCancelled):
        run_summary(
            transcript,
            shipped_variant(transcript.style_id),
            RunSettings("sum-model", 8192),
            summarizer_factory=lambda **kwargs: Cancelling(),
        )
