"""Shared SLM triage prompt ``triage.v1`` (spec v1.1 §9.4, A-16).

One renderer serves E3 zero-shot now, the SFT targets (P3) and the serving parity tests (P4):

* ``ml/prompts/triage.v1.txt`` holds a static system section and a user section with three
  placeholders. The system text is byte-identical for every request (prefix-cacheable); only
  the user message varies.
* The ticket (subject, earlier messages, latest message) is rendered only inside the
  ``<ticket-{nonce}>`` block, after neutralization: chat-template special-token literals
  (``<|im_end|>``, ``<start_of_turn>`` ...) and any ``<ticket-`` / ``</ticket-`` tag lose their
  leading ``<`` (it becomes ``&lt;``), so ticket text can neither forge a chat role in a raw
  prompt nor close the delimiter block. The metadata line carries only enum values and a
  timestamp, never free text.
* The nonce is injected by the caller: :func:`new_nonce` (random, serving) or
  :func:`derive_nonce` (keyed hash of the record id, for offline evaluation and training, so
  reruns render byte-identical prompts). It is 16 lowercase hex characters and must not occur
  in the ticket text.
* The assistant target is ``TriageLabels.model_dump_json()``: minified, keys in contract order,
  which is the decoding-schema order (``schemas/json/triage_model_output.decoding.json``).

Rendering is deterministic: the same prompt file, ticket, labels and nonce always give the same
messages, target and hash. Errors never echo ticket text.
"""

import hashlib
import json
import re
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import ValidationError

from tw_ml.datagen.paths import find_repo_root
from tw_ml.datagen.records import DatasetRecord, TicketPayload, TriageLabels, utc_iso

PROMPT_VERSION: Final = "triage.v1"
PROMPTS_SUBDIR: Final = Path("ml") / "prompts"
PLACEHOLDERS: Final[frozenset[str]] = frozenset({"metadata_json", "nonce", "ticket"})
PLACEHOLDER: Final = re.compile(r"\{\{([a-z_]+)\}\}")
NONCE_PATTERN: Final = re.compile(r"^[0-9a-f]{16}$")
ESCAPED_LT: Final = "&lt;"
DEFAULT_SPECIAL_LITERALS: Final[tuple[str, ...]] = (
    "<start_of_turn>",
    "<end_of_turn>",
    "<bos>",
    "<eos>",
    "<pad>",
    "<unk>",
    "<s>",
    "</s>",
    "<think>",
    "</think>",
    "<tool_call>",
    "</tool_call>",
    "<tool_response>",
    "</tool_response>",
)
"""Bare-tag control tokens of the bake-off families (Gemma, Llama/Mistral, Qwen).

Bar-shaped tokens (``<|im_start|>``, ``<|eot_id|>``, ``<|end|>``, Gemma 4 ``<|turn>`` and
``<turn|>``) are caught by a pattern instead, so reserved and future ones are covered too.
"""

BAR_TOKEN: Final = re.compile(r"<\|[^\s<>|]{1,64}\|?>|<[^\s<>|]{1,64}\|>")
"""Bar-shaped control tokens (``<|x|>``, ``<|x>``, ``<x|>``); :func:`neutralize_ticket_text`
breaks every match, so model families need not list them."""

_SECTION: Final = re.compile(r"^--- (system|user) ---\s*$")
_BAR_TOKEN: Final = re.compile(r"<(?=\|[^\s<>|]{1,64}\|?>|[^\s<>|]{1,64}\|>)")
_DELIMITER: Final = re.compile(r"<(?=/?ticket-)", re.IGNORECASE)
_NONCE_DOMAIN: Final = "tw-triage-nonce"


class PromptError(ValueError):
    """Raised for malformed prompt files, bad nonces or unusable rows (no ticket text)."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One chat message.

    Attributes:
        role: ``system``, ``user`` or ``assistant`` (the training target).
        content: Message text.
    """

    role: Literal["system", "user", "assistant"]
    content: str


def new_nonce() -> str:
    """A random per-request nonce for serving (64 bits from ``secrets``).

    Returns:
        16 lowercase hex characters.
    """
    return secrets.token_hex(8)


def derive_nonce(key: str, *, salt: str) -> str:
    """A reproducible nonce for offline evaluation and training.

    Args:
        key: Per-item key, e.g. the record id.
        salt: Run-level salt (config version and seed), so different runs differ.

    Returns:
        16 lowercase hex characters.
    """
    payload = "\x1f".join((_NONCE_DOMAIN, salt, key)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _escape_first(literal: str) -> str:
    head = ESCAPED_LT if literal[0] == "<" else f"&#{ord(literal[0])};"
    return head + literal[1:]


def neutralize_ticket_text(text: str, special_tokens: Iterable[str] = ()) -> str:
    """Break every special-token literal and delimiter tag in untrusted ticket text.

    Line endings are normalized to LF. Only the first character of each match changes (``<``
    becomes ``&lt;``), so the text stays readable and a second pass changes nothing.

    Args:
        text: Ticket text (subject, message or an earlier message body).
        special_tokens: Extra literals of the target model family (``PromptFormat``).

    Returns:
        The neutralized text.
    """
    out = text.replace("\r\n", "\n").replace("\r", "\n")
    out = _BAR_TOKEN.sub(ESCAPED_LT, out)
    out = _DELIMITER.sub(ESCAPED_LT, out)
    literals = {t for t in (*DEFAULT_SPECIAL_LITERALS, *special_tokens) if t and not t.isspace()}
    for literal in sorted(literals, key=lambda t: (-len(t), t)):
        out = out.replace(literal, _escape_first(literal))
    return out


def metadata_line(ticket: TicketPayload) -> str:
    """The metadata JSON line: form fields only (enum values and a timestamp, no free text).

    Args:
        ticket: The ticket.

    Returns:
        Compact JSON with keys ``customer_tier``, ``channel``, ``product_area_hint`` and
        ``received_at`` (in this order; ``null`` when absent).
    """
    product = ticket.product
    document = {
        "customer_tier": ticket.customer_tier,
        "channel": ticket.channel,
        "product_area_hint": product.product_area_hint if product is not None else None,
        "received_at": utc_iso(ticket.received_at) if ticket.received_at is not None else None,
    }
    return json.dumps(document, separators=(",", ":"))


def ticket_block(ticket: TicketPayload, special_tokens: Iterable[str] = ()) -> str:
    """The text inside the delimiters: subject, earlier messages (oldest first), latest message.

    Args:
        ticket: The ticket.
        special_tokens: Extra literals to neutralize (see :func:`neutralize_ticket_text`).

    Returns:
        The neutralized ticket text.
    """
    literals = tuple(special_tokens)
    history = ticket.previous_messages
    lines = [f"subject: {neutralize_ticket_text(ticket.subject, literals)}"]
    for number, message in enumerate(history, start=1):
        header = f"earlier message {number} of {len(history)}"
        lines.append(f"{header} ({message.author}, {utc_iso(message.sent_at)}):")
        lines.append(neutralize_ticket_text(message.body, literals))
    lines.append("latest customer message:")
    lines.append(neutralize_ticket_text(ticket.message, literals))
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class RenderedTriagePrompt:
    """One rendered triage request (and, for training, its target).

    Attributes:
        prompt_version: Prompt version (``triage.v1``).
        prompt_sha256: Hash of the prompt file (mirrored into ``prompt_versions``).
        nonce: The delimiter id used.
        system: System message (static).
        user: User message: metadata line and the delimited ticket.
        target: Minified ``TriageLabels`` JSON in contract key order, or ``None`` without labels.
        sha256: Hash of system, user and target (determinism checks).
    """

    prompt_version: str
    prompt_sha256: str
    nonce: str
    system: str
    user: str
    target: str | None
    sha256: str

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        """System and user messages (the inference request)."""
        return (ChatMessage("system", self.system), ChatMessage("user", self.user))

    def chat(self, *, with_target: bool = False) -> list[dict[str, str]]:
        """Messages as ``{"role", "content"}`` dicts (``apply_chat_template``, chat APIs).

        Args:
            with_target: Append the assistant target (training rows).

        Returns:
            The conversation.

        Raises:
            PromptError: If the target is requested but the render had no labels.
        """
        conversation = [{"role": m.role, "content": m.content} for m in self.messages]
        if with_target:
            if self.target is None:
                msg = "this prompt was rendered without labels; there is no target"
                raise PromptError(msg)
            conversation.append({"role": "assistant", "content": self.target})
        return conversation


@dataclass(frozen=True, slots=True)
class TriagePrompt:
    """A parsed triage prompt file.

    Attributes:
        version: File stem (``triage.v1``), recorded as ``prompt_version``.
        system: The static system message.
        user_template: The user message with ``{{metadata_json}}``, ``{{nonce}}``, ``{{ticket}}``.
        prompt_sha256: SHA-256 of the LF-normalized file text.
    """

    version: str
    system: str
    user_template: str
    prompt_sha256: str

    def render(
        self,
        ticket: TicketPayload,
        *,
        nonce: str,
        labels: TriageLabels | None = None,
        special_tokens: Iterable[str] = (),
    ) -> RenderedTriagePrompt:
        """Render one request.

        Args:
            ticket: The ticket (already PII-masked upstream).
            nonce: Delimiter id from :func:`new_nonce` or :func:`derive_nonce`.
            labels: Gold labels, to also produce the training target.
            special_tokens: Extra special-token literals of the target model family.

        Returns:
            The rendered prompt.

        Raises:
            PromptError: If the nonce is malformed or occurs in the ticket text.
        """
        if not NONCE_PATTERN.fullmatch(nonce):
            msg = "the nonce must be 16 lowercase hex characters"
            raise PromptError(msg)
        block = ticket_block(ticket, special_tokens)
        if nonce in block.lower():
            msg = "the nonce occurs in the ticket text; draw a new one"
            raise PromptError(msg)
        values = {"metadata_json": metadata_line(ticket), "nonce": nonce, "ticket": block}
        user = PLACEHOLDER.sub(lambda match: values[match.group(1)], self.user_template)
        target = labels.model_dump_json() if labels is not None else None
        payload = json.dumps([self.system, user, target], ensure_ascii=False)
        return RenderedTriagePrompt(
            prompt_version=self.version,
            prompt_sha256=self.prompt_sha256,
            nonce=nonce,
            system=self.system,
            user=user,
            target=target,
            sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )

    def render_record(
        self,
        record: DatasetRecord | Mapping[str, Any],
        *,
        nonce: str,
        special_tokens: Iterable[str] = (),
    ) -> RenderedTriagePrompt:
        """Render a dataset record or an evaluation row, with its target when it has labels.

        Args:
            record: A ``DatasetRecord`` or a row with ``ticket`` and optional ``labels``
                (hard-set, e2e and smoke rows).
            nonce: Delimiter id.
            special_tokens: Extra special-token literals of the target model family.

        Returns:
            The rendered prompt.

        Raises:
            PromptError: If the row has no valid ticket or its labels are invalid.
        """
        labels: TriageLabels | None
        if isinstance(record, DatasetRecord):
            ticket, labels = record.ticket, record.labels
        else:
            part = "ticket"
            try:
                ticket = TicketPayload.model_validate(record.get("ticket"))
                part, raw = "labels", record.get("labels")
                labels = TriageLabels.model_validate(raw) if raw is not None else None
            except ValidationError as exc:
                where = sorted({".".join((part, *map(str, e["loc"]))) for e in exc.errors()})
                msg = f"invalid row at {', '.join(where[:5])}"
                raise PromptError(msg) from None
        return self.render(ticket, nonce=nonce, labels=labels, special_tokens=special_tokens)


def parse_triage_prompt(text: str, version: str) -> TriagePrompt:
    """Parse a triage prompt file.

    Args:
        text: File content: ``#`` comment lines, then ``--- system ---`` and ``--- user ---``.
        version: File stem.

    Returns:
        The prompt.

    Raises:
        PromptError: If a section is missing, repeated or out of order, text precedes the
            system section, the system section has placeholders, or the user section does not
            use exactly the three placeholders.
    """
    normalized = text.replace("\r\n", "\n")
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for number, line in enumerate(normalized.split("\n"), start=1):
        header = _SECTION.match(line)
        if header:
            name = header.group(1)
            if name in sections or (name == "user" and "system" not in sections):
                msg = f"{version} line {number}: sections must be system, then user, once each"
                raise PromptError(msg)
            sections[name], current = [], name
        elif current is not None:
            sections[current].append(line)
        elif line.strip() and not line.startswith("#"):
            msg = f"{version} line {number}: only comments may precede the system section"
            raise PromptError(msg)
    if set(sections) != {"system", "user"}:
        msg = f"{version}: needs a system and a user section"
        raise PromptError(msg)
    system, user = ("\n".join(sections[name]).strip() for name in ("system", "user"))
    if PLACEHOLDER.search(system):
        msg = f"{version}: the system section must be static (no placeholders)"
        raise PromptError(msg)
    if set(PLACEHOLDER.findall(user)) != PLACEHOLDERS:
        msg = f"{version}: the user section must use exactly {sorted(PLACEHOLDERS)}"
        raise PromptError(msg)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return TriagePrompt(version=version, system=system, user_template=user, prompt_sha256=digest)


def load_triage_prompt(
    version: str = PROMPT_VERSION, prompts_dir: Path | None = None
) -> TriagePrompt:
    """Load ``ml/prompts/<version>.txt``.

    Args:
        version: Prompt version (file stem).
        prompts_dir: Directory override (defaults to the repository's ``ml/prompts``).

    Returns:
        The parsed prompt.

    Raises:
        PromptError: If the file is missing or malformed.
    """
    path = (prompts_dir or find_repo_root() / PROMPTS_SUBDIR) / f"{version}.txt"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        msg = f"prompt file not found: {version}.txt"
        raise PromptError(msg) from None
    return parse_triage_prompt(text, version)
