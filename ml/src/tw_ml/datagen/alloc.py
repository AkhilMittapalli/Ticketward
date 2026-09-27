"""Deterministic allocation, seeding and stratified sampling helpers.

Every random choice in the data pipeline goes through :func:`rng_for`, which derives a
``random.Random`` from a blake2b hash of explicit parts (``seed``, split, cell id...). The
results are therefore identical across processes, machines and Python 3.12/3.13, and a
change to one cell never shifts the random stream of another.
"""

import hashlib
import random
from collections import defaultdict
from collections.abc import Callable, Hashable, Mapping, Sequence


def derive_seed(*parts: object) -> int:
    """Derive a 63-bit seed from arbitrary parts.

    Args:
        *parts: Values whose ``str()`` forms identify the random stream.

    Returns:
        A non-negative integer below 2**63.
    """
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big") >> 1


def rng_for(*parts: object) -> random.Random:
    """Return a ``random.Random`` seeded from ``parts`` (see :func:`derive_seed`).

    Args:
        *parts: Values that identify the random stream.

    Returns:
        An independent, deterministic generator (not for cryptographic use).
    """
    return random.Random(derive_seed(*parts))  # noqa: S311 - reproducible sampling, not crypto


def largest_remainder(weights: Mapping[str, float], total: int) -> dict[str, int]:
    """Apportion ``total`` units to keys proportionally (Hamilton / largest remainder).

    Ties in the remainders are broken by the mapping's key order, so the result is fully
    deterministic.

    Args:
        weights: Non-negative weights; keys with weight 0 receive 0.
        total: Units to distribute (>= 0).

    Returns:
        Key to integer count; the counts sum to ``total``.

    Raises:
        ValueError: If a weight is negative, ``total`` is negative, or every weight is 0
            while ``total`` > 0.
    """
    if total < 0 or any(w < 0 for w in weights.values()):
        msg = "weights and total must be non-negative"
        raise ValueError(msg)
    weight_sum = sum(weights.values())
    if total == 0:
        return dict.fromkeys(weights, 0)
    if weight_sum <= 0:
        msg = "cannot apportion a positive total over zero weights"
        raise ValueError(msg)
    exact = {key: total * w / weight_sum for key, w in weights.items()}
    counts = {key: int(value) for key, value in exact.items()}
    order = {key: index for index, key in enumerate(weights)}
    leftover = total - sum(counts.values())
    by_remainder = sorted(exact, key=lambda key: (-(exact[key] - counts[key]), order[key]))
    for key in by_remainder[:leftover]:
        counts[key] += 1
    return counts


def group_by[T, K: Hashable](items: Sequence[T], key: Callable[[T], K]) -> dict[K, list[T]]:
    """Group items by key, preserving input order inside each group.

    Args:
        items: Items to group.
        key: Stratum key function.

    Returns:
        Stratum to items (strata in first-seen order).
    """
    groups: dict[K, list[T]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    return dict(groups)


def stratified_sample[T](
    items: Sequence[T],
    *,
    key: Callable[[T], Hashable],
    n: int,
    seed: int,
    sort_key: Callable[[T], str],
) -> list[T]:
    """Draw a proportional stratified sample without replacement.

    Stratum sizes are apportioned with :func:`largest_remainder`; items inside a stratum are
    chosen by a seeded shuffle of the items sorted by ``sort_key``, so the input order never
    changes the result.

    Args:
        items: Population.
        key: Stratum key function.
        n: Sample size (capped at the population size).
        seed: Sampling seed (recorded by the caller).
        sort_key: Stable identity (e.g. ``record_id``) used before shuffling.

    Returns:
        The sample, ordered by stratum then by the seeded shuffle.
    """
    ordered = sorted(items, key=sort_key)
    strata = group_by(ordered, key)
    target = min(n, len(ordered))
    names = sorted(strata, key=str)
    sizes = {str(name): float(len(strata[name])) for name in names}
    counts = largest_remainder(sizes, target)
    sample: list[T] = []
    for name in names:
        members = list(strata[name])
        rng_for(seed, "stratum", str(name)).shuffle(members)
        sample.extend(members[: counts[str(name)]])
    return sample


def stratified_split[T](
    items: Sequence[T],
    *,
    key: Callable[[T], Hashable],
    first_size: int,
    seed: int,
    sort_key: Callable[[T], str],
) -> tuple[list[T], list[T]]:
    """Split items into two parts, stratified by ``key``.

    Args:
        items: Population.
        key: Stratum key function.
        first_size: Size of the first part.
        seed: Split seed.
        sort_key: Stable identity used before shuffling.

    Returns:
        ``(first, rest)`` where ``first`` has ``first_size`` items; both parts keep the
        population's ``sort_key`` order.
    """
    first = stratified_sample(items, key=key, n=first_size, seed=seed, sort_key=sort_key)
    chosen = {sort_key(item) for item in first}
    ordered = sorted(items, key=sort_key)
    return (
        [item for item in ordered if sort_key(item) in chosen],
        [item for item in ordered if sort_key(item) not in chosen],
    )
