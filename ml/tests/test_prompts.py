"""Prompt families P-A and P-B: structure, determinism and what they must never contain."""

import re

import pytest

from tw_ml.datagen.generate import GenerationContext
from tw_ml.datagen.leakage import kb_texts, read_protected_strings
from tw_ml.datagen.matrix import GenerationPlan
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.prompts import (
    PA_FILE,
    PA_VARIABLES,
    PB_FILE,
    PB_STAGE1_VARIABLES,
    PB_STAGE2_VARIABLES,
    PLACEHOLDER,
    PromptError,
    RenderedPrompt,
    entities_text,
    history_text,
    label_rules_text,
    load_prompt_family,
    output_schema_text,
    parse_prompt_family,
    render_pa,
    render_pb_stage1,
    render_pb_stage2,
    render_text,
    stage_templates,
)
from tw_ml.datagen.records import GenerationCell, ScenarioFacts, TriageLabels
from tw_ml.datagen.taxonomy import Taxonomy
from tw_ml.datagen.text import normalize, window_hashes, word_tokens

SCENARIO = ScenarioFacts(
    timeline=("A thing happened.", "Another thing happened."),
    customer_goal="Make it work again.",
    facts_customer_knows=("It started this morning.",),
)


def _sample(plan: GenerationPlan, per_template: int = 6) -> list[GenerationCell]:
    chosen: dict[str, list[GenerationCell]] = {}
    for cell in plan.cells:
        bucket = chosen.setdefault(cell.template_id, [])
        if len(bucket) < per_template:
            bucket.append(cell)
    special = [
        next(c for c in plan.cells if c.injection),
        next(c for c in plan.cells if c.secondary_intents),
        next(c for c in plan.cells if c.competitor),
        next(c for c in plan.cells if c.pii_placeholders),
        next(c for c in plan.cells if c.channel == "chat_transcript"),
    ]
    return [c for bucket in chosen.values() for c in bucket] + special


def _pa_prompts(ctx: GenerationContext, plan: GenerationPlan) -> list[RenderedPrompt]:
    return [render_pa(cell, ctx.prompt_context, ctx.family) for cell in _sample(plan)]


def _pb_prompts(ctx: GenerationContext, plan: GenerationPlan) -> list[RenderedPrompt]:
    rendered: list[RenderedPrompt] = []
    for cell in _sample(plan):
        rendered.append(render_pb_stage1(cell, ctx.prompt_context, ctx.family))
        rendered.append(render_pb_stage2(cell, ctx.prompt_context, ctx.family, SCENARIO))
    return rendered


def _text(prompt: RenderedPrompt) -> str:
    return "\n".join(m.content for m in prompt.messages)


# --------------------------------------------------------------------------- structure


def test_families_hold_the_expected_templates(paths: RepoPaths) -> None:
    pa = load_prompt_family(PA_FILE, paths.prompts_dir)
    pb = load_prompt_family(PB_FILE, paths.prompts_dir)
    assert sorted(pa.templates) == [f"pa.t{i}" for i in range(1, 7)]
    assert sorted(pb.templates) == ["pb.m1", "pb.m2", "pb.s1", "pb.s2"]
    for template in pa.templates.values():
        assert template.placeholders == PA_VARIABLES, template.template_id
    for template in pb.templates.values():
        expected = PB_STAGE1_VARIABLES if ".s" in template.template_id else PB_STAGE2_VARIABLES
        assert template.placeholders == expected, template.template_id
    assert pa.sha256 != pb.sha256


def test_templates_are_distinct_paraphrases(paths: RepoPaths) -> None:
    pa = load_prompt_family(PA_FILE, paths.prompts_dir)
    systems = {t.system for t in pa.templates.values()}
    users = {t.user for t in pa.templates.values()}
    assert len(systems) == len(users) == 6


def test_parser_errors() -> None:
    with pytest.raises(PromptError, match="twice"):
        parse_prompt_family(
            "=== template pa.t1 ===\n--- system ---\na\n--- user ---\nb\n=== template pa.t1 ===\n",
            "x",
        )
    with pytest.raises(PromptError, match="system and a user"):
        parse_prompt_family("=== template pa.t1 ===\n--- system ---\nonly system\n", "x")
    family = parse_prompt_family(
        "# header comment\n=== template pa.t9 ===\n--- system ---\nS\n--- user ---\nU {{x}}\n",
        "x.v1",
    )
    with pytest.raises(PromptError, match="no template"):
        family.template("pa.t1")
    with pytest.raises(PromptError, match="no value"):
        render_text("hello {{missing}}", {})
    assert render_text('{"json": {{v}}}', {"v": "1"}) == '{"json": 1}'
    with pytest.raises(PromptError, match="pair"):
        stage_templates("pb.s1")
    assert stage_templates("pb.s2+pb.m2") == ("pb.s2", "pb.m2")


# --------------------------------------------------------------------------- rendering


def test_p_a_rendering_is_complete_and_deterministic(
    val_ctx: GenerationContext, val_plan: GenerationPlan
) -> None:
    for cell in _sample(val_plan, per_template=3):
        first = render_pa(cell, val_ctx.prompt_context, val_ctx.family)
        second = render_pa(cell, val_ctx.prompt_context, val_ctx.family)
        assert first == second
        text = _text(first)
        assert not PLACEHOLDER.search(text)
        assert val_ctx.facts.prompt_text.strip() in text
        assert cell.intent in text
        for value in cell.display_values:
            assert value in text
        if cell.injection:
            assert cell.injection in text
        assert first.prompt_version == "pa_persona.v1"
        assert first.template_id == cell.template_id


def test_different_cells_render_differently(
    val_ctx: GenerationContext, val_plan: GenerationPlan
) -> None:
    hashes = {
        render_pa(c, val_ctx.prompt_context, val_ctx.family).sha256 for c in val_plan.cells[:40]
    }
    assert len(hashes) == 40


def test_p_b_prompts_never_name_a_label(
    test_ctx: GenerationContext, test_plan: GenerationPlan, taxonomy: Taxonomy
) -> None:
    labels = [
        *taxonomy.values("Intent"),
        *taxonomy.values("Queue"),
        *taxonomy.values("RecommendedAction"),
    ]
    for prompt in _pb_prompts(test_ctx, test_plan):
        text = _text(prompt)
        assert not PLACEHOLDER.search(text)
        for label in labels:
            assert not re.search(rf"\b{re.escape(label)}\b", text), (prompt.template_id, label)
        assert "proposed_labels" not in text


def test_p_b_stage_two_uses_the_stage_one_facts(
    test_ctx: GenerationContext, test_plan: GenerationPlan
) -> None:
    cell = next(c for c in test_plan.cells if c.injection)
    stage2 = _text(render_pb_stage2(cell, test_ctx.prompt_context, test_ctx.family, SCENARIO))
    assert "A thing happened." in stage2
    assert "It started this morning." in stage2
    assert cell.injection is not None
    assert cell.injection in stage2
    stage1 = _text(render_pb_stage1(cell, test_ctx.prompt_context, test_ctx.family))
    assert test_ctx.facts.prompt_text.strip() in stage1
    assert cell.injection not in stage1  # the injected text belongs to the customer's message


# --------------------------------------------------------------------------- never in a prompt


@pytest.fixture(scope="module")
def protected(paths: RepoPaths) -> list[str]:
    return read_protected_strings(paths.spec_dir / "protected_strings.txt")


def _shares_protected_text(text: str, entries: list[str]) -> list[str]:
    windows = window_hashes(word_tokens(text), 8)
    normalized = normalize(text)
    hits = []
    for entry in entries:
        tokens = word_tokens(entry)
        if window_hashes(tokens, 8) & windows or (
            len(tokens) >= 5 and normalize(entry) in normalized
        ):
            hits.append(entry)
    return hits


def test_prompts_contain_no_protected_example(
    val_ctx: GenerationContext,
    val_plan: GenerationPlan,
    test_ctx: GenerationContext,
    test_plan: GenerationPlan,
    protected: list[str],
) -> None:
    prompts = _pa_prompts(val_ctx, val_plan) + _pb_prompts(test_ctx, test_plan)
    for prompt in prompts:
        assert _shares_protected_text(_text(prompt), protected) == [], prompt.template_id


def test_static_prompt_sources_contain_no_protected_example(
    paths: RepoPaths, protected: list[str]
) -> None:
    for source in (
        paths.prompts_dir / f"{PA_FILE}.txt",
        paths.prompts_dir / f"{PB_FILE}.txt",
        paths.spec_dir / "fact_sheet.v1.md",
    ):
        assert _shares_protected_text(source.read_text(encoding="utf-8"), protected) == [], (
            source.name
        )


def test_prompts_contain_no_knowledge_base_text(
    paths: RepoPaths, val_ctx: GenerationContext, val_plan: GenerationPlan
) -> None:
    # The KB is written later in P1; this guard starts biting as soon as it exists.
    kb = kb_texts(paths.kb_dir)
    kb_windows = {v for text in kb.values() for v in window_hashes(word_tokens(text), 12)}
    for prompt in _pa_prompts(val_ctx, val_plan):
        assert not window_hashes(word_tokens(_text(prompt)), 12) & kb_windows


def test_prompts_never_embed_example_tickets(
    val_ctx: GenerationContext, val_plan: GenerationPlan
) -> None:
    for prompt in _pa_prompts(val_ctx, val_plan):
        system = prompt.messages[0].content
        assert "example ticket" not in system.lower()
        assert not re.search(r"(?m)^\s*(?:Subject|From|Dear)\s*:", system)


# --------------------------------------------------------------------------- shared text


def test_label_rules_text_lists_every_intent_and_rule(
    val_ctx: GenerationContext, taxonomy: Taxonomy
) -> None:
    text = label_rules_text(val_ctx.prompt_context)
    for intent in taxonomy.values("Intent"):
        assert f"- {intent}: " in text
    for phrase in (
        "CRITICAL INTENTS",
        "SECONDARY INTENTS",
        "ACTION OVERRIDES",
        "CHURN RISK",
        "ENTITIES",
    ):
        assert phrase in text
    assert "offer_human_contact" in text
    assert "request_more_information" in text


def test_output_schema_follows_the_contract_key_order() -> None:
    text = output_schema_text()
    positions = [text.index(f'"{name}"') for name in TriageLabels.model_fields]
    assert positions == sorted(positions)
    assert text.index('"subject"') < text.index('"proposed_labels"') < text.index('"self_check"')


def test_entity_and_history_text(val_plan: GenerationPlan) -> None:
    sso = next(c for c in val_plan.cells if any(e.type == "saml_idp" for e in c.entities))
    assert "saml_idp; label value" in entities_text(sso, with_types=True)
    assert "saml_idp" not in entities_text(sso, with_types=False)
    chat = next(c for c in val_plan.cells if c.channel == "chat_transcript")
    assert "chat turns" in history_text(chat)
    quiet = next(c for c in val_plan.cells if c.history_len == 0)
    assert history_text(quiet) == "none"
    assert (
        entities_text(
            quiet.model_copy(update={"entities": (), "display_values": ()}), with_types=True
        )
        == "none"
    )
