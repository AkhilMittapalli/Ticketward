"""tw_ml.eval.stats: known answers, published reference values, determinism and coverage."""

import math

import numpy as np
import pytest
from scipy import stats as sps
from sklearn.metrics import f1_score

from tw_ml.datagen import qa
from tw_ml.eval import stats
from tw_ml.eval.stats import (
    accuracy_rows,
    benjamini_hochberg,
    bootstrap,
    bootstrap_distribution,
    clopper_pearson_interval,
    encode,
    exact_lower_bound,
    holm,
    macro_f1_rows,
    mcnemar,
    micro_f1_rows,
    paired_bootstrap,
    proportion,
    randomization_pvalue,
    resample_indices,
    seed_mean_bootstrap,
    seed_summary,
    wilson_interval,
    z_for,
)

# --------------------------------------------------------------------------- proportions

# Newcombe (1998), Stat Med 17:857-872, Table I, method 3 (Wilson score, no correction).
NEWCOMBE_WILSON = [
    (81, 263, 0.2553, 0.3662),
    (15, 148, 0.0624, 0.1605),
    (0, 20, 0.0000, 0.1611),
    (1, 29, 0.0061, 0.1718),
]
# ERPROT evaluation-statistics F2 (computed from the same formulas).
ERPROT_WILSON = [(57, 60, 0.863, 0.983), (5, 5, 0.566, 1.0), (4, 5, 0.376, 0.964)]
ERPROT_EXACT = [
    (57, 60, 0.861, 0.990),
    (5, 5, 0.478, 1.0),
    (4, 5, 0.284, 0.995),
    (90, 100, 0.824, 0.951),
]


@pytest.mark.parametrize(("k", "n", "low", "high"), NEWCOMBE_WILSON)
def test_wilson_matches_newcombe_1998(k: int, n: int, low: float, high: float) -> None:
    got = wilson_interval(k, n)
    assert got == pytest.approx((low, high), abs=1e-4)


@pytest.mark.parametrize(("k", "n", "low", "high"), ERPROT_WILSON)
def test_wilson_matches_research_table(k: int, n: int, low: float, high: float) -> None:
    assert wilson_interval(k, n) == pytest.approx((low, high), abs=1e-3)


@pytest.mark.parametrize(("k", "n", "low", "high"), ERPROT_EXACT)
def test_clopper_pearson_matches_research_table(k: int, n: int, low: float, high: float) -> None:
    assert clopper_pearson_interval(k, n) == pytest.approx((low, high), abs=1e-3)


@pytest.mark.parametrize("n", [7, 40, 263])
def test_intervals_match_scipy_binomtest(n: int) -> None:
    for k in range(0, n + 1, max(1, n // 7)):
        result = sps.binomtest(k, n)
        wilson = result.proportion_ci(confidence_level=0.95, method="wilson")
        exact = result.proportion_ci(confidence_level=0.95, method="exact")
        assert wilson_interval(k, n) == pytest.approx((wilson.low, wilson.high), abs=1e-9)
        assert clopper_pearson_interval(k, n) == pytest.approx((exact.low, exact.high), abs=1e-9)


def test_proportion_uses_exact_at_the_extremes() -> None:
    assert proportion(3, 10).method == "wilson"
    assert proportion(0, 10).method == "clopper-pearson"
    full = proportion(10, 10)
    assert (full.method, full.point, full.high, full.k, full.n) == (
        "clopper-pearson",
        1.0,
        1.0,
        10,
        10,
    )
    empty = proportion(0, 0)
    assert empty.point is None
    assert empty.low is None
    assert empty.method.startswith("undefined")


@pytest.mark.parametrize(("n", "bound"), [(60, 0.9513), (250, 0.9881), (385, 0.9922)])
def test_m07a_lower_bound_is_the_exact_zero_failure_bound(n: int, bound: float) -> None:
    assert exact_lower_bound(n, n) == pytest.approx(0.05 ** (1 / n), rel=1e-12)
    assert exact_lower_bound(n, n) == pytest.approx(sps.beta.ppf(0.05, n, 1), rel=1e-9)
    assert exact_lower_bound(n, n) == pytest.approx(bound, abs=1e-4)
    assert 1 - exact_lower_bound(n, n) == pytest.approx(3 / n, rel=0.1)  # rule of three


def test_exact_lower_bound_general_case() -> None:
    assert exact_lower_bound(0, 12) == 0.0
    assert exact_lower_bound(1, 3) == pytest.approx(1 - 0.95 ** (1 / 3))
    assert exact_lower_bound(47, 50) == pytest.approx(sps.beta.ppf(0.05, 47, 4))
    assert exact_lower_bound(49, 50) < exact_lower_bound(50, 50)


def test_invalid_inputs_raise() -> None:
    assert z_for(0.95) == pytest.approx(1.959964, abs=1e-6)
    with pytest.raises(ValueError, match="level"):
        z_for(1.0)
    with pytest.raises(ValueError, match="n > 0"):
        wilson_interval(3, 2)
    with pytest.raises(ValueError, match="n > 0"):
        exact_lower_bound(0, 0)
    with pytest.raises(ValueError, match="vocabulary"):
        encode(["b"], ["a"])


def _covers(k: int, n: int, p: float) -> bool:
    interval = proportion(k, n)
    assert interval.low is not None
    assert interval.high is not None
    return interval.low <= p <= interval.high


def test_wilson_coverage_is_near_nominal() -> None:
    """Exact coverage by binomial enumeration (no simulation noise)."""
    for p, n in ((0.3, 50), (0.85, 120)):
        coverage = sum(sps.binom.pmf(k, n, p) for k in range(n + 1) if _covers(k, n, p))
        assert 0.92 <= coverage <= 0.99


# --------------------------------------------------------------------------- vectorized metrics


@pytest.mark.parametrize("seed", range(8))
def test_macro_f1_rows_equals_sklearn(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n_classes, labels = 6, np.array([0, 1, 2, 3, 4], dtype=np.int64)  # class 5 = "__invalid__"
    gold = rng.integers(0, 5, size=(4, 60), dtype=np.int64)
    pred = np.where(rng.random((4, 60)) < 0.6, gold, rng.integers(0, 6, size=(4, 60)))
    gold[:, :10] = 0  # class 4 may vanish from a row: sklearn still scores it 0
    rows = macro_f1_rows(gold, pred, n_classes, labels)
    for r in range(4):
        expected = f1_score(gold[r], pred[r], labels=labels, average="macro", zero_division=0)
        assert rows[r] == pytest.approx(expected)
    assert accuracy_rows(gold, pred) == pytest.approx((gold == pred).mean(axis=1))


def test_micro_f1_rows_on_ticket_counts() -> None:
    counts = np.array([[2, 0, 0], [1, 1, 0], [0, 0, 1]], dtype=np.int64)  # tp, fp, fn
    identity = np.arange(3, dtype=np.int64)[None, :]
    assert micro_f1_rows(counts, identity)[0] == pytest.approx(6 / 8)
    empty = np.zeros((2, 3), dtype=np.int64)
    assert math.isnan(micro_f1_rows(empty, np.array([[0, 1]], dtype=np.int64))[0])


def test_stratified_resampling_keeps_every_stratum() -> None:
    strata = np.array([0, 0, 0, 1, 1, 2, 2, 2, 2], dtype=np.int64)
    draws = resample_indices(strata.size, 500, np.random.default_rng(1), strata)
    assert draws.shape == (500, 9)
    for column, stratum in enumerate(strata):
        assert set(strata[draws[:, column]]) == {stratum}
    counts = np.stack([np.bincount(strata[row], minlength=3) for row in draws])
    assert (counts == np.bincount(strata)).all()
    with pytest.raises(ValueError, match="one code per record"):
        resample_indices(4, 2, np.random.default_rng(0), strata)


def _mean_statistic(values: stats.FloatArray) -> stats.RowStatistic:
    def statistic(indices: stats.IntArray) -> stats.FloatArray:
        return np.asarray(values[indices].mean(axis=1), dtype=np.float64)

    return statistic


def test_bootstrap_is_deterministic_and_seeded() -> None:
    values = np.random.default_rng(3).normal(size=200)
    first = bootstrap(_mean_statistic(values), 200, n_resamples=2_500, seed=11)
    again = bootstrap(_mean_statistic(values), 200, n_resamples=2_500, seed=11)
    other = bootstrap(_mean_statistic(values), 200, n_resamples=2_500, seed=12)
    assert first == again
    assert first != other
    assert first.point == pytest.approx(values.mean())
    assert first.low is not None
    assert first.high is not None
    assert first.point is not None
    assert first.low < first.point < first.high
    assert (first.n_resamples, first.rng_seed, first.method) == (2_500, 11, "percentile-bootstrap")
    strata = (values > 0).astype(np.int64)
    assert bootstrap(_mean_statistic(values), 200, strata=strata, n_resamples=50).method.startswith(
        "stratified-"
    )
    assert bootstrap(_mean_statistic(values), 0).point is None
    with pytest.raises(ValueError, match="n_resamples"):
        bootstrap_distribution(_mean_statistic(values), 200, n_resamples=0)


def test_bootstrap_ci_coverage_sanity() -> None:
    """Percentile CI of a Bernoulli mean covers the truth about 95% of the time."""
    rng = np.random.default_rng(2026)
    hits = 0
    for trial in range(300):
        sample = (rng.random(100) < 0.3).astype(np.float64)
        interval = bootstrap(_mean_statistic(sample), 100, n_resamples=400, seed=trial)
        assert interval.low is not None
        assert interval.high is not None
        hits += interval.low <= 0.3 <= interval.high
    assert 0.88 <= hits / 300 <= 0.99


# --------------------------------------------------------------------------- paired tests


def _accuracy_metric(gold: stats.IntArray, pred: stats.IntArray) -> stats.FloatArray:
    return accuracy_rows(gold, pred)


def test_paired_bootstrap_of_identical_systems_is_zero() -> None:
    values = np.random.default_rng(5).normal(size=80)
    same = _mean_statistic(values)
    interval = paired_bootstrap(same, same, 80, n_resamples=300)
    assert (interval.point, interval.low, interval.high) == (0.0, 0.0, 0.0)
    shifted = _mean_statistic(values + 1.0)
    delta = paired_bootstrap(shifted, same, 80, n_resamples=300)
    assert delta.point == pytest.approx(1.0)
    assert delta.method == "paired-percentile-bootstrap"


def test_randomization_pvalue() -> None:
    rng = np.random.default_rng(9)
    gold = rng.integers(0, 3, size=150, dtype=np.int64)
    good = np.where(rng.random(150) < 0.9, gold, (gold + 1) % 3)
    bad = np.where(rng.random(150) < 0.5, gold, (gold + 1) % 3)
    assert randomization_pvalue(gold, good, good, _accuracy_metric, n_resamples=500) == 1.0
    better = randomization_pvalue(
        gold, good, bad, _accuracy_metric, n_resamples=2_000, alternative="greater"
    )
    assert better < 0.01
    worse = randomization_pvalue(
        gold, bad, good, _accuracy_metric, n_resamples=2_000, alternative="greater"
    )
    assert worse > 0.9
    assert randomization_pvalue(gold, good, bad, _accuracy_metric, n_resamples=300, seed=4) == (
        randomization_pvalue(gold, good, bad, _accuracy_metric, n_resamples=300, seed=4)
    )
    with pytest.raises(ValueError, match="equally long"):
        randomization_pvalue(gold, good[:-1], bad, _accuracy_metric)


def _exact_mcnemar(b: int, c: int) -> float:
    n, k = b + c, min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1))
    return min(1.0, float(2 * tail) / float(2**n))


@pytest.mark.parametrize(
    ("b", "c", "exact", "midp"),
    [(18, 8, 0.0755, 0.0522), (22, 8, 0.0161, 0.0107), (60, 40, 0.0569, 0.0460)],
)
def test_mcnemar_known_answers(b: int, c: int, exact: float, midp: float) -> None:
    a_correct = [True] * b + [False] * c + [True] * 30
    b_correct = [False] * b + [True] * c + [True] * 30
    result = mcnemar(a_correct, b_correct)
    assert (result.n10, result.n01) == (b, c)
    assert result.p_exact == pytest.approx(exact, abs=1e-4)
    assert result.p_exact == pytest.approx(_exact_mcnemar(b, c))
    assert result.p_midp == pytest.approx(midp, abs=1e-4)
    assert result.p_midp < result.p_exact


def test_mcnemar_edge_cases() -> None:
    assert mcnemar([True, False], [True, False]).p_midp == 1.0
    tied = mcnemar([True, False, True, False], [False, True, False, True])
    assert tied.p_exact == 1.0
    assert tied.p_midp == pytest.approx(1.0)
    chi = mcnemar([True] * 18 + [False] * 8, [False] * 18 + [True] * 8)
    assert chi.p_chi2 == pytest.approx(0.0499, abs=1e-4)
    with pytest.raises(ValueError, match="equal length"):
        mcnemar([True], [True, False])


def test_holm_known_answer() -> None:
    adjusted, reject = holm([0.01, 0.04, 0.03, 0.005])
    assert adjusted == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert reject == [True, False, False, True]
    assert holm([]) == ([], [])
    assert holm([0.2, 0.9]) == ([0.4, 0.9], [False, False])
    with pytest.raises(ValueError, match="p-values"):
        holm([1.5])


def test_benjamini_hochberg_matches_scipy() -> None:
    pvalues = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205]
    expected = sps.false_discovery_control(pvalues, method="bh")
    assert benjamini_hochberg(pvalues) == pytest.approx(list(expected))


# --------------------------------------------------------------------------- seeds


def test_seed_summary_chi_square_multipliers() -> None:
    summary = seed_summary({"42": 0.80, "1337": 0.82, "2026": 0.84})
    assert summary.mean == pytest.approx(0.82)
    assert summary.sd == pytest.approx(0.02)
    assert summary.sd_low is not None
    assert summary.sd_high is not None
    assert summary.sd is not None
    assert summary.sd_low / summary.sd == pytest.approx(0.521, abs=1e-3)
    assert summary.sd_high / summary.sd == pytest.approx(6.285, abs=1e-3)
    assert (summary.minimum, summary.maximum, summary.n_seeds) == (0.80, 0.84, 3)
    single = seed_summary({"42": 0.7})
    assert single.sd is None
    with pytest.raises(ValueError, match="at least one seed"):
        seed_summary({})


def test_seed_mean_bootstrap_centres_on_the_mean() -> None:
    rng = np.random.default_rng(1)
    per_seed = [rng.normal(loc=mu, size=60) for mu in (0.0, 0.1, 0.2)]
    interval = seed_mean_bootstrap([_mean_statistic(v) for v in per_seed], 60, n_resamples=400)
    assert interval.point == pytest.approx(np.mean([v.mean() for v in per_seed]))
    assert interval.method == "two-level-percentile-bootstrap"
    with pytest.raises(ValueError, match="at least one seed"):
        seed_mean_bootstrap([], 60)


def test_qa_keeps_its_p1_api_on_the_shared_math() -> None:
    assert qa.wilson_interval(57, 60) == stats.wilson_bounds(57, 60, qa.Z_95)
    assert qa.cohen_kappa(["a", "b", "a"], ["a", "b", "b"]) == stats.cohen_kappa(
        ["a", "b", "a"], ["a", "b", "b"]
    )
    assert math.isnan(stats.cohen_kappa(["a"], ["a"]))
