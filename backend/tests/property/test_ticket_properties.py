"""Property-based tests: ``TicketCreate`` enforces its size limits for any content."""

from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from ticketward.schemas.ticket import (
    EXTERNAL_ID_MAX_CHARS,
    MESSAGE_MAX_CHARS,
    PREVIOUS_MESSAGES_MAX,
    SUBJECT_MAX_CHARS,
    TicketCreate,
)

# Letters, digits and punctuation only: no whitespace, so stripping cannot change length
# and Python/Rust whitespace definitions cannot diverge.
VISIBLE = st.characters(categories=("L", "N", "P"))
LOWERCASE = st.characters(categories=["Ll"])


def base(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "customer_tier": "starter",
        "channel": "web_form",
        "subject": "Recurring tasks",
        "message": "How do I set up recurring tasks for my team?",
    }
    payload.update(overrides)
    return payload


def error_locs(exc: ValidationError) -> set[tuple[tuple[str | int, ...], str]]:
    return {(tuple(error["loc"]), error["type"]) for error in exc.errors()}


def long_text(min_size: int, extra: int) -> st.SearchStrategy[str]:
    """Strings of ``min_size`` to ``min_size + extra`` visible characters.

    Built as random head + repeated filler so large sizes stay cheap to generate.
    """
    return st.builds(
        lambda head, filler, size: (head + filler * size)[:size],
        st.text(VISIBLE, min_size=1, max_size=40),
        VISIBLE,
        st.integers(min_value=min_size, max_value=min_size + extra),
    )


@given(subject=st.text(VISIBLE, min_size=1, max_size=SUBJECT_MAX_CHARS))
def test_subjects_within_limit_are_accepted_verbatim(subject: str) -> None:
    assert TicketCreate.model_validate(base(subject=subject)).subject == subject


@given(subject=long_text(SUBJECT_MAX_CHARS + 1, 500))
def test_oversize_subjects_are_always_rejected(subject: str) -> None:
    assert len(subject) > SUBJECT_MAX_CHARS
    with pytest.raises(ValidationError) as excinfo:
        TicketCreate.model_validate(base(subject=subject))
    assert (("subject",), "string_too_long") in error_locs(excinfo.value)


@settings(max_examples=25, deadline=None)
@given(message=long_text(MESSAGE_MAX_CHARS + 1, 5_000))
def test_oversize_messages_are_always_rejected(message: str) -> None:
    assert len(message) > MESSAGE_MAX_CHARS
    with pytest.raises(ValidationError) as excinfo:
        TicketCreate.model_validate(base(message=message))
    assert (("message",), "string_too_long") in error_locs(excinfo.value)


@given(external_id=long_text(EXTERNAL_ID_MAX_CHARS + 1, 200))
def test_oversize_external_ids_are_always_rejected(external_id: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        TicketCreate.model_validate(base(external_id=external_id))
    assert (("external_id",), "string_too_long") in error_locs(excinfo.value)


@settings(max_examples=20, deadline=None)
@given(count=st.integers(min_value=PREVIOUS_MESSAGES_MAX + 1, max_value=PREVIOUS_MESSAGES_MAX + 30))
def test_oversize_histories_are_always_rejected(count: int) -> None:
    message = {"author": "customer", "body": "still broken", "sent_at": "2026-09-26T12:00:00Z"}
    with pytest.raises(ValidationError) as excinfo:
        TicketCreate.model_validate(base(previous_messages=[message] * count))
    assert (("previous_messages",), "too_long") in error_locs(excinfo.value)


@given(
    core=st.text(VISIBLE, min_size=1, max_size=SUBJECT_MAX_CHARS),
    left=st.integers(min_value=0, max_value=50),
    right=st.integers(min_value=0, max_value=50),
)
def test_surrounding_whitespace_is_stripped_before_length_checks(
    core: str, left: int, right: int
) -> None:
    padded = " " * left + core + "\t" * right
    assert TicketCreate.model_validate(base(subject=padded)).subject == core


@given(extra_key=st.text(LOWERCASE, min_size=1, max_size=20))
def test_unknown_top_level_fields_are_always_rejected(extra_key: str) -> None:
    assume(extra_key not in TicketCreate.model_fields)
    with pytest.raises(ValidationError) as excinfo:
        TicketCreate.model_validate({**base(), extra_key: "x"})
    assert ((extra_key,), "extra_forbidden") in error_locs(excinfo.value)
