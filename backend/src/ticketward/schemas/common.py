"""Shared contract primitives.

``ContractModel`` is the base for every API/model contract: unknown fields are
rejected (``extra="forbid"``) and input values are hidden from ``ValidationError``
string representations so ticket text never leaks into logs or tracebacks.

The aliases below are plain (implicit) type aliases on purpose: Pydantic inlines
them, which keeps the exported JSON Schemas flat for constrained decoding (§6.6).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ArrBand = Literal["<10k", "10k-50k", "50k-250k", ">250k"]
"""Synthetic account ARR band (spec §3)."""

Region = Literal["us", "eu", "apac"]
"""Synthetic account region (spec §3)."""

Platform = Literal["web", "ios", "android", "desktop", "api"]
"""Client platform hint (spec §6.1)."""

Prob = Annotated[float, Field(ge=0.0, le=1.0)]
"""Probability in ``[0, 1]`` (spec §6.2 ``Prob``)."""

ChurnSignal = Annotated[str, Field(max_length=200)]
"""One churn cue quoted or paraphrased from the ticket (spec §5.5: at most 200 chars)."""

DocKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,127}$")]
"""Stable knowledge-base document slug, e.g. ``kb_sso_redirect_loop`` (spec §8.2)."""


class ContractModel(BaseModel):
    """Base model for all data contracts."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
