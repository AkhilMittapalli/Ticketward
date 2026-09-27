"""Generator prompt families P-A (persona-first) and P-B (scenario-first), spec v1.1 §9.1.

Prompts are versioned files in ``ml/prompts/datagen/`` (``pa_persona.v1.txt``,
``pb_scenario.v1.txt``); each holds several template variants whose ids (``pa.t1`` ...) are the
``template_id`` recorded in provenance and checked for split disjointness (leakage C4).

Rendering is a pure function of the template, the plan cell, the fact sheet, the label rules
and the pools: the same inputs always give the same messages (and the same hash). The only
product context a prompt ever carries is the fact sheet; no knowledge-base text and no example
tickets exist in any input of this module. P-B prompts never name a label: the generator does
not label test data (gold labels come from the scenario spec plus human review).
"""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from tw_ml.datagen.factsheet import FactSheet
from tw_ml.datagen.labelrules import LabelRules
from tw_ml.datagen.matrix import Matrix
from tw_ml.datagen.paths import default_paths
from tw_ml.datagen.pools import Pools
from tw_ml.datagen.records import GenerationCell, ScenarioFacts, TriageLabels
from tw_ml.datagen.taxonomy import Taxonomy

PA_FILE: Final = "pa_persona.v1"
PB_FILE: Final = "pb_scenario.v1"
PLACEHOLDER: Final = re.compile(r"\{\{([a-z_]+)\}\}")
_TEMPLATE_HEADER: Final = re.compile(r"^=== template ([a-z]{2}\.[a-z0-9]+) ===\s*$")
_SECTION_HEADER: Final = re.compile(r"^--- (system|user) ---\s*$")

PA_VARIABLES: Final[frozenset[str]] = frozenset(
    {
        "fact_sheet", "label_rules", "output_schema", "persona_name", "persona_role",
        "company_name", "company_seats", "plan", "region", "persona_habits", "intent",
        "intent_definition", "secondary", "secondary_order", "product_area", "channel",
        "channel_hint", "difficulty", "difficulty_hint", "impact", "sentiment", "churn_cue",
        "entities", "omissions", "human_request", "injection", "legal_threat", "history",
        "target_words", "length_bucket", "style", "style_hint", "subject_style", "subject_hint",
        "greeting", "banned_words", "placeholders",
    }
)  # fmt: skip
PB_STAGE1_VARIABLES: Final[frozenset[str]] = frozenset(
    {
        "fact_sheet", "company_name", "plan", "company_seats", "region", "scenario_type",
        "additional_needs", "timeline_anchor", "systems", "entities", "attempts", "unknowns",
        "severity", "account_context", "persona_first_name", "persona_role",
    }
)  # fmt: skip
PB_STAGE2_VARIABLES: Final[frozenset[str]] = frozenset(
    {
        "timeline", "customer_goal", "facts_known", "entities", "persona_first_name",
        "persona_role", "company_name", "sentiment", "human_request_phrase", "churn_phrase",
        "legal_phrase", "framing", "needs_order", "channel", "channel_hint", "history",
        "target_words", "style_hint", "subject_hint", "greeting", "banned_words",
        "placeholders", "injection",
    }
)  # fmt: skip

PRIORITY_DEFINITIONS: Final[Mapping[str, str]] = {
    "urgent": "org-wide blocker, security incident, outage, data loss, enterprise production down",
    "high": (
        "blocks a team or workflow, payment failure with suspension risk, frustrated enterprise"
    ),
    "normal": "single-user issue with a workaround, billing question",
    "low": "how-to, feature request, cosmetic",
}
"""Spec §5.3 definitions (labels are assigned before any policy floor)."""

_ORDER_TEXT: Final[Mapping[str, str]] = {
    "primary_first": "mention the primary need first",
    "secondary_first": "mention a secondary need first and the primary need after it",
    "interleaved": "interleave the needs",
}
_ORDER_TEXT_PB: Final[Mapping[str, str]] = {
    "primary_first": "your main problem first, then the rest",
    "secondary_first": "a side matter first, then your main problem",
    "interleaved": "mix the points together",
}
_ACCOUNT_CONTEXT: Final[Mapping[str, str]] = {
    "none": "no change to the subscription is planned",
    "vague_alternatives": "the team has started to look at other tools but has decided nothing",
    "repeated_contact": "the customer has contacted support about this before",
    "explicit_cancel": "the customer has decided to stop using Taskmoor at the end of the term",
    "competitor": "the customer has decided to move to {competitor}",
    "ultimatum": "the customer will leave unless this is resolved by a deadline",
}
_CHURN_PHRASE: Final[Mapping[str, str]] = {
    "none": "",
    "vague_alternatives": (
        "You mention that your team is looking at other tools, without having decided anything."
    ),
    "repeated_contact": (
        "You mention that this is not the first time you have contacted support about it."
    ),
    "explicit_cancel": (
        "You state clearly that you want to stop using Taskmoor (end it, not renew, terminate, "
        "or move to the free plan)."
    ),
    "competitor": "You say that you are moving to {competitor}.",
    "ultimatum": "You give an ultimatum: you will leave unless this is resolved by a deadline.",
}
_HUMAN_PHRASE: Final[Mapping[str, str]] = {
    "none": "",
    "direct": "You explicitly ask to speak with a person, a manager or a human agent.",
    "indirect": (
        "You would like a person to take over but only hint at it, for example by asking for a "
        "call, without the words human, person or agent."
    ),
}
_LEGAL_TEXT: Final = "the customer says legal action may follow if this is not resolved"
_LEGAL_PHRASE: Final = "You say that legal action may follow if this is not resolved."
_OUTPUT_TYPES: Final[Mapping[str, str]] = {
    "intent": '"<Intent>"',
    "secondary_intents": '["<Intent>", at most 2]',
    "priority": '"<Priority>"',
    "sentiment": '"<Sentiment>"',
    "churn_risk": '"<ChurnRisk>"',
    "churn_signals": '["<cue from the ticket, at most 200 chars>", at most 5]',
    "product_area": '"<ProductArea>"',
    "entities": '[{"type": "<EntityType>", "value": "<exact text from the ticket>"}, at most 20]',
    "recommended_queue": '"<Queue>"',
    "recommended_action": '"<RecommendedAction>"',
    "customer_requested_human": "true | false",
    "information_sufficient": "true | false",
    "rationale": '"<one or two sentences, at most 400 chars>"',
}


class PromptError(ValueError):
    """Raised for malformed prompt files or unresolved placeholders."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One chat message sent to a generator.

    Attributes:
        role: ``system`` or ``user``.
        content: Message text.
    """

    role: Literal["system", "user"]
    content: str


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """One template variant of a family.

    Attributes:
        template_id: Id recorded in provenance (e.g. ``pa.t1``).
        system: System message with ``{{placeholders}}``.
        user: User message with ``{{placeholders}}``.
    """

    template_id: str
    system: str
    user: str

    @property
    def placeholders(self) -> frozenset[str]:
        """Every placeholder name used by the template."""
        return frozenset(PLACEHOLDER.findall(self.system) + PLACEHOLDER.findall(self.user))


@dataclass(frozen=True, slots=True)
class PromptFamily:
    """A versioned prompt file.

    Attributes:
        version: File stem, recorded as ``prompt_version`` (e.g. ``pa_persona.v1``).
        templates: Template id to template.
        sha256: Hash of the file text.
    """

    version: str
    templates: Mapping[str, PromptTemplate]
    sha256: str

    def template(self, template_id: str) -> PromptTemplate:
        """Return one template.

        Args:
            template_id: Template id.

        Returns:
            The template.

        Raises:
            PromptError: If the family has no such template.
        """
        try:
            return self.templates[template_id]
        except KeyError:
            msg = f"{self.version} has no template {template_id!r}"
            raise PromptError(msg) from None


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """A fully rendered request.

    Attributes:
        template_id: Template used.
        prompt_version: Family version.
        messages: Messages in order.
        sha256: Hash of the messages (deterministic rendering check).
    """

    template_id: str
    prompt_version: str
    messages: tuple[ChatMessage, ...]
    sha256: str

    def text(self) -> str:
        """Render the messages as one reviewable text block (used by ``--dry-run``).

        Returns:
            Role headers followed by message contents.
        """
        return "\n".join(f"[{m.role.upper()}]\n{m.content}\n" for m in self.messages)


@dataclass(frozen=True, slots=True)
class PromptContext:
    """Static inputs of every rendering.

    Attributes:
        taxonomy: Taxonomy (label enums).
        rules: Label rules.
        matrix: Generation matrix (definitions and descriptions).
        facts: Fact sheet.
        pools: Pools of the split being generated.
    """

    taxonomy: Taxonomy
    rules: LabelRules
    matrix: Matrix
    facts: FactSheet
    pools: Pools


def parse_prompt_family(text: str, version: str) -> PromptFamily:
    """Parse a prompt family file.

    Args:
        text: File content.
        version: Family version (the file stem).

    Returns:
        The parsed family.

    Raises:
        PromptError: If a template lacks a section or appears twice.
    """
    templates: dict[str, dict[str, list[str]]] = {}
    current: str | None = None
    section: str | None = None
    for line in text.replace("\r\n", "\n").split("\n"):
        header = _TEMPLATE_HEADER.match(line)
        if header:
            current, section = header.group(1), None
            if current in templates:
                msg = f"{version}: template {current} defined twice"
                raise PromptError(msg)
            templates[current] = {"system": [], "user": []}
            continue
        if current is None:
            continue  # file header comments
        part = _SECTION_HEADER.match(line)
        if part:
            section = part.group(1)
        elif section is not None:
            templates[current][section].append(line)
    parsed: dict[str, PromptTemplate] = {}
    for template_id, sections in templates.items():
        system, user = ("\n".join(sections[s]).strip() for s in ("system", "user"))
        if not system or not user:
            msg = f"{version}: template {template_id} needs a system and a user section"
            raise PromptError(msg)
        parsed[template_id] = PromptTemplate(template_id, system, user)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return PromptFamily(version=version, templates=parsed, sha256=digest)


def load_prompt_family(version: str, prompts_dir: Path | None = None) -> PromptFamily:
    """Load ``<prompts_dir>/<version>.txt``.

    Args:
        version: Family version (file stem).
        prompts_dir: Directory override (defaults to ``ml/prompts/datagen``).

    Returns:
        The parsed family.
    """
    path = (prompts_dir or default_paths().prompts_dir) / f"{version}.txt"
    return parse_prompt_family(path.read_text(encoding="utf-8"), version)


def render_text(template: str, variables: Mapping[str, str]) -> str:
    """Substitute ``{{name}}`` placeholders.

    Args:
        template: Text with placeholders.
        variables: Name to value.

    Returns:
        The rendered text.

    Raises:
        PromptError: If a placeholder has no value.
    """

    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            msg = f"no value for placeholder {name!r}"
            raise PromptError(msg)
        return variables[name]

    return PLACEHOLDER.sub(value, template)


def render_template(
    family: PromptFamily, template_id: str, variables: Mapping[str, str]
) -> RenderedPrompt:
    """Render one template into chat messages.

    Args:
        family: Prompt family.
        template_id: Template to render.
        variables: Placeholder values.

    Returns:
        The rendered prompt.
    """
    template = family.template(template_id)
    messages = (
        ChatMessage("system", render_text(template.system, variables)),
        ChatMessage("user", render_text(template.user, variables)),
    )
    payload = json.dumps([[m.role, m.content] for m in messages], ensure_ascii=False)
    return RenderedPrompt(
        template_id=template_id,
        prompt_version=family.version,
        messages=messages,
        sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


def stage_templates(template_id: str) -> tuple[str, str]:
    """Split a P-B pair id (``pb.s1+pb.m1``) into its stage-1 and stage-2 template ids.

    Args:
        template_id: Pair id from the matrix.

    Returns:
        ``(stage1, stage2)``.

    Raises:
        PromptError: If the id is not a pair.
    """
    parts = template_id.split("+")
    if len(parts) != 2:  # noqa: PLR2004 - a pair has exactly two stages
        msg = f"{template_id!r} is not a stage-1+stage-2 template pair"
        raise PromptError(msg)
    return parts[0], parts[1]


# --------------------------------------------------------------------------- shared text


def label_rules_text(ctx: PromptContext) -> str:
    """Compact label rules for P-A (enums with one-line definitions + guideline rules).

    Contains definitions only: no example tickets and no guideline examples.

    Args:
        ctx: Prompt context.

    Returns:
        Multi-line rules text.
    """
    tax, rules, spec = ctx.taxonomy, ctx.rules, ctx.matrix.spec
    intents = [f"- {i}: {spec.intents[i].definition}" for i in tax.values("Intent")]
    routing = [
        f"- {i}: queue {rules.routing[i].queue}; action {rules.routing[i].action}"
        for i in tax.values("Intent")
    ]
    keeps = sorted(rules.forced_review_intents | rules.insufficient_info_keeps_default)
    areas = ", ".join(f"{a} ({ctx.facts.area_names[a]})" for a in tax.values("ProductArea"))
    priorities = "; ".join(f"{p} = {PRIORITY_DEFINITIONS[p]}" for p in tax.values("Priority"))
    lines = [
        "INTENTS (primary = what the customer needs resolved first):",
        *intents,
        "CRITICAL INTENTS (always the primary when the ticket also has a non-critical need): "
        + ", ".join(i for i in tax.values("Intent") if rules.is_critical(i)),
        "SECONDARY INTENTS: at most 2, no duplicates, never the primary, never other_unclear.",
        "DEFAULT QUEUE AND ACTION PER PRIMARY INTENT:",
        *routing,
        f"ACTION OVERRIDES: customer_requested_human = true -> {rules.human_request_action}. "
        f"information_sufficient = false -> {rules.insufficient_info_action}, except for "
        f"{', '.join(keeps)}, which keep their default action.",
        "VALID QUEUES: " + ", ".join(tax.values("Queue")),
        "VALID ACTIONS: " + ", ".join(tax.values("RecommendedAction")),
        f"PRIORITY (what the ticket implies, before any policy floor): {priorities}.",
        "SENTIMENT of the latest customer message: " + ", ".join(tax.values("Sentiment")) + ".",
        "CHURN RISK: high only with an explicit intent to cancel, not renew, terminate or "
        "downgrade to free, a named competitor they are moving to, or an ultimatum; medium for "
        "vague talk of other tools, repeated contacts, or a frustrated or angry customer on the "
        "business or enterprise plan; low otherwise. churn_signals: up to 5 short cues from the "
        "ticket.",
        f"PRODUCT AREAS: {areas}.",
        "ENTITIES: types " + ", ".join(tax.values("EntityType")) + ". Copy values exactly as "
        "written in the ticket and never infer one. saml_idp values are "
        + ", ".join(tax.values("SamlIdp"))
        + ". Never extract personal data; placeholders such as <EMAIL_1> stay as they are.",
        "customer_requested_human: true for a direct or an indirect request for a person.",
        "information_sufficient: false when the details needed for the first action are missing.",
        "rationale: one or two short sentences; no step-by-step reasoning.",
    ]
    return "\n".join(lines)


def output_schema_text() -> str:
    """The P-A response skeleton, with label keys in the contract (decoding) order.

    Returns:
        A compact, typed JSON skeleton.
    """
    labels = ",\n    ".join(
        f'"{name}": {_OUTPUT_TYPES[name]}' for name in TriageLabels.model_fields
    )
    return (
        '{"subject": "<string, 1-300 characters>",\n'
        ' "message": "<the latest customer message>",\n'
        ' "previous_messages": [{"author": "customer" | "agent", "body": "<string>"}],\n'
        f' "proposed_labels": {{\n    {labels}}},\n'
        ' "self_check": {"card_satisfied": true | false, "note": "<string>"}}'
    )


def entities_text(cell: GenerationCell, *, with_types: bool) -> str:
    """List the values a ticket must contain verbatim.

    Args:
        cell: Plan cell.
        with_types: Add the entity type (P-A) or give bare values (P-B).

    Returns:
        A one-line list, or ``none``.
    """
    parts: list[str] = []
    for entity, display in zip(cell.entities, cell.display_values, strict=True):
        if not with_types:
            parts.append(f'"{display}"')
        elif entity.type == "saml_idp":
            parts.append(f'"{display}" (saml_idp; label value {entity.value})')
        else:
            parts.append(f'"{display}" ({entity.type})')
    return ", ".join(parts) or "none"


def history_text(cell: GenerationCell) -> str:
    """Describe the earlier messages a thread must have.

    Args:
        cell: Plan cell.

    Returns:
        ``none`` or a short instruction.
    """
    if cell.history_len == 0:
        return "none"
    if cell.channel == "chat_transcript":
        return (
            f"{cell.history_len} earlier chat turns in previous_messages, alternating customer "
            "and agent; the message is the customer's final turn"
        )
    return f"{cell.history_len} earlier messages in previous_messages (customer and agent)"


def _common(cell: GenerationCell, ctx: PromptContext) -> dict[str, str]:
    persona = ctx.pools.persona(cell.persona_id)
    company = ctx.pools.company(cell.company_id)
    described = ctx.matrix.spec.descriptions
    return {
        "company_name": company.name,
        "company_seats": str(company.seats),
        "plan": cell.plan,
        "region": ctx.facts.regions.get(company.region, company.region),
        "persona_role": persona.role,
        "persona_first_name": persona.first_name,
        "persona_name": persona.full_name,
        "persona_habits": "; ".join(persona.habits),
        "channel": cell.channel,
        "channel_hint": described.channel[cell.channel],
        "sentiment": cell.sentiment,
        "history": history_text(cell),
        "target_words": str(cell.target_words),
        "style_hint": described.style[cell.style],
        "subject_hint": described.subject_style[cell.subject_style],
        "greeting": "yes" if cell.greeting_allowed else "no",
        "banned_words": ", ".join(f'"{w}"' for w in cell.banned_words) or "none",
        "placeholders": " ".join(cell.pii_placeholders) or "none",
        "injection": f'"{cell.injection}"' if cell.injection else "none",
    }


# --------------------------------------------------------------------------- P-A


def pa_variables(cell: GenerationCell, ctx: PromptContext) -> dict[str, str]:
    """Placeholder values of a P-A card.

    Args:
        cell: Plan cell.
        ctx: Prompt context.

    Returns:
        Variable name to value (exactly :data:`PA_VARIABLES`).
    """
    described = ctx.matrix.spec.descriptions
    churn = described.churn_cue[cell.churn_cue]
    if cell.competitor:
        churn = f"{churn} (competitor: {cell.competitor})"
    variables = _common(cell, ctx)
    variables.update(
        {
            "fact_sheet": ctx.facts.prompt_text,
            "label_rules": label_rules_text(ctx),
            "output_schema": output_schema_text(),
            "intent": cell.intent,
            "intent_definition": ctx.matrix.spec.intents[cell.intent].definition,
            "secondary": ", ".join(cell.secondary_intents) or "none",
            "secondary_order": (
                _ORDER_TEXT[cell.secondary_order] if cell.secondary_order else "not applicable"
            ),
            "product_area": cell.product_area,
            "difficulty": cell.difficulty,
            "difficulty_hint": described.difficulty[cell.difficulty],
            "impact": described.impact[cell.priority_hint],
            "churn_cue": churn,
            "entities": entities_text(cell, with_types=True),
            "omissions": "; ".join(cell.omissions) or "nothing",
            "human_request": described.human_request[cell.human_request],
            "legal_threat": _LEGAL_TEXT if cell.legal_threat else "none",
            "length_bucket": cell.length_bucket,
            "style": cell.style,
            "subject_style": cell.subject_style,
        }
    )
    variables.pop("persona_first_name")
    return variables


def render_pa(cell: GenerationCell, ctx: PromptContext, family: PromptFamily) -> RenderedPrompt:
    """Render the P-A request for a cell.

    Args:
        cell: Plan cell (its ``template_id`` picks the variant).
        ctx: Prompt context.
        family: The P-A family.

    Returns:
        The rendered prompt.
    """
    return render_template(family, cell.template_id, pa_variables(cell, ctx))


# --------------------------------------------------------------------------- P-B


def pb_stage1_variables(cell: GenerationCell, ctx: PromptContext) -> dict[str, str]:
    """Placeholder values of a P-B stage-1 (case timeline) request.

    Args:
        cell: Plan cell.
        ctx: Prompt context.

    Returns:
        Variable name to value (exactly :data:`PB_STAGE1_VARIABLES`).
    """
    spec = ctx.matrix.spec
    common = _common(cell, ctx)
    attempts = next((e.value for e in cell.entities if e.type == "steps_already_tried"), None)
    systems = [
        ctx.facts.area_names[cell.product_area],
        *([cell.feature_name] if cell.feature_name else []),
    ]
    context = _ACCOUNT_CONTEXT[cell.churn_cue].format(competitor=cell.competitor or "")
    variables = {
        "fact_sheet": ctx.facts.prompt_text,
        "scenario_type": cell.scenario_type or "a general question to support",
        "additional_needs": "; ".join(spec.intents[s].need_phrase for s in cell.secondary_intents)
        or "none",
        "timeline_anchor": f"the customer writes on {cell.received_at:%Y-%m-%d} at "
        f"{cell.received_at:%H:%M} UTC",
        "systems": ", ".join(systems),
        "entities": entities_text(cell, with_types=False),
        "attempts": attempts or "nothing recorded",
        "unknowns": "; ".join(cell.omissions) or "nothing in particular",
        "severity": spec.descriptions.impact[cell.priority_hint],
        "account_context": context,
    }
    variables.update({k: common[k] for k in PB_STAGE1_VARIABLES & common.keys()})
    return variables


def pb_stage2_variables(
    cell: GenerationCell, ctx: PromptContext, scenario: ScenarioFacts
) -> dict[str, str]:
    """Placeholder values of a P-B stage-2 (customer message) request.

    Args:
        cell: Plan cell.
        ctx: Prompt context.
        scenario: Stage-1 output.

    Returns:
        Variable name to value (exactly :data:`PB_STAGE2_VARIABLES`).
    """
    competitor = cell.competitor or ""
    order = _ORDER_TEXT_PB[cell.secondary_order] if cell.secondary_order else "as it comes"
    variables = {
        "timeline": " | ".join(scenario.timeline),
        "customer_goal": scenario.customer_goal,
        "facts_known": " | ".join(scenario.facts_customer_knows) or "only the timeline above",
        "entities": entities_text(cell, with_types=False),
        "human_request_phrase": _HUMAN_PHRASE[cell.human_request],
        "churn_phrase": _CHURN_PHRASE[cell.churn_cue].format(competitor=competitor),
        "legal_phrase": _LEGAL_PHRASE if cell.legal_threat else "",
        "framing": ctx.matrix.spec.descriptions.difficulty[cell.difficulty],
        "needs_order": order,
    }
    common = _common(cell, ctx)
    variables.update({k: common[k] for k in PB_STAGE2_VARIABLES & common.keys()})
    return variables


def render_pb_stage1(
    cell: GenerationCell, ctx: PromptContext, family: PromptFamily
) -> RenderedPrompt:
    """Render the P-B stage-1 request.

    Args:
        cell: Plan cell (its pair id picks the variant).
        ctx: Prompt context.
        family: The P-B family.

    Returns:
        The rendered prompt.
    """
    stage1, _ = stage_templates(cell.template_id)
    return render_template(family, stage1, pb_stage1_variables(cell, ctx))


def render_pb_stage2(
    cell: GenerationCell, ctx: PromptContext, family: PromptFamily, scenario: ScenarioFacts
) -> RenderedPrompt:
    """Render the P-B stage-2 request.

    Args:
        cell: Plan cell.
        ctx: Prompt context.
        family: The P-B family.
        scenario: Stage-1 output.

    Returns:
        The rendered prompt.
    """
    _, stage2 = stage_templates(cell.template_id)
    return render_template(family, stage2, pb_stage2_variables(cell, ctx, scenario))
