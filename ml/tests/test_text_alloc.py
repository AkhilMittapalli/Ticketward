"""Normalization, hashing and deterministic allocation helpers."""

import random
from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tw_ml.datagen.alloc import (
    derive_seed,
    group_by,
    largest_remainder,
    rng_for,
    stratified_sample,
    stratified_split,
)
from tw_ml.datagen.text import (
    char_shingles,
    content_sha256,
    h64,
    jaccard,
    join_customer_text,
    normalization_id,
    normalize,
    sha256_hex,
    window_hashes,
    word_tokens,
)


@given(st.text())
def test_normalize_is_idempotent(text: str) -> None:
    assert normalize(normalize(text)) == normalize(text)


def test_normalize_rewrites_placeholders_before_lowercasing() -> None:
    assert normalize("Mail <EMAIL_12> and <PERSON_1>") == "mail <email> and <person>"
    assert normalize("Invoice INV-A123456 for $1,280.50") == "invoice inv-a0 for $0,0.0"
    assert normalize("  many\t\nspaces  ") == "many spaces"
    assert normalize("ﬁle") == "file"  # NFKC
    assert normalization_id() == "nfkc|placeholders|lower|digits0|ws"


def test_hashes_are_stable() -> None:
    assert sha256_hex("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert content_sha256("Hello  WORLD 42") == content_sha256("hello world 7")
    assert h64(["a", "b"]) == h64(["a", "b"]) != h64(["b", "a"])
    assert derive_seed("x", 1) == derive_seed("x", 1) != derive_seed("x", 2)
    assert 0 <= derive_seed("anything") < 2**63


def test_shingles_windows_and_jaccard() -> None:
    assert char_shingles("abc") == frozenset({"abc"})
    assert len(char_shingles("abcdefg")) == 3
    assert jaccard(frozenset(), frozenset()) == 1.0
    assert jaccard(frozenset({"a", "b"}), frozenset({"b", "c"})) == pytest.approx(1 / 3)
    tokens = word_tokens("One two three four")
    assert tokens == ["one", "two", "three", "four"]
    assert len(window_hashes(tokens, 2)) == 3
    assert window_hashes(tokens, 5) == set()
    assert join_customer_text("s", "m", ["p1", "p2"]) == "s\nm\np1\np2"


@given(
    st.dictionaries(st.text(min_size=1, max_size=4), st.floats(0.01, 100), min_size=1, max_size=8),
    st.integers(0, 500),
)
def test_largest_remainder_sums_and_stays_within_one(weights: dict[str, float], total: int) -> None:
    counts = largest_remainder(weights, total)
    assert sum(counts.values()) == total
    weight_sum = sum(weights.values())
    for key, count in counts.items():
        exact = total * weights[key] / weight_sum
        assert exact - 1 < count < exact + 1


def test_largest_remainder_ties_follow_key_order_and_rejects_bad_input() -> None:
    assert largest_remainder({"a": 1, "b": 1, "c": 1}, 2) == {"a": 1, "b": 1, "c": 0}
    assert largest_remainder({"a": 0, "b": 0}, 0) == {"a": 0, "b": 0}
    with pytest.raises(ValueError, match="non-negative"):
        largest_remainder({"a": -1}, 3)
    with pytest.raises(ValueError, match="zero weights"):
        largest_remainder({"a": 0}, 3)


def test_rng_for_is_deterministic_and_independent() -> None:
    assert rng_for(1, "a").random() == rng_for(1, "a").random()
    assert rng_for(1, "a").random() != rng_for(1, "b").random()


def test_stratified_sample_is_proportional_and_order_independent() -> None:
    items = [
        f"{stratum}-{i:03d}"
        for stratum, size in (("x", 60), ("y", 30), ("z", 10))
        for i in range(size)
    ]
    shuffled = items[:]
    random.Random(4).shuffle(shuffled)  # noqa: S311 - seeded shuffle of test data, not security
    first = stratified_sample(items, key=lambda s: s[0], n=20, seed=9, sort_key=str)
    second = stratified_sample(shuffled, key=lambda s: s[0], n=20, seed=9, sort_key=str)
    assert first == second
    assert Counter(s[0] for s in first) == {"x": 12, "y": 6, "z": 2}
    assert len(set(first)) == 20
    everything = stratified_sample(items, key=lambda s: s[0], n=500, seed=9, sort_key=str)
    assert sorted(everything) == sorted(items)  # n is capped at the population size
    assert stratified_sample(items, key=lambda s: s[0], n=20, seed=10, sort_key=str) != first


def test_stratified_split_partitions() -> None:
    items = [f"{k}-{i}" for k in "abc" for i in range(10)]
    first, rest = stratified_split(items, key=lambda s: s[0], first_size=9, seed=1, sort_key=str)
    assert len(first) == 9
    assert sorted(first + rest) == sorted(items)
    assert Counter(s[0] for s in first) == {"a": 3, "b": 3, "c": 3}
    assert group_by(items, lambda s: s[0])["b"][0] == "b-0"
