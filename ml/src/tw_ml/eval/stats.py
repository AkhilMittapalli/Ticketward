"""Interval estimates, bootstrap resampling and paired tests (spec v1.1 §9.8, A-10; ADR-0032).

Implements the ERPROT ``evaluation-statistics`` protocol:

* proportions: Wilson score intervals, Clopper-Pearson (exact) when ``k = 0`` or ``k = n``,
  and the one-sided exact lower bound, which is ``0.05 ** (1 / n)`` when all ``n`` items
  succeed (M-07a);
* non-decomposable metrics (macro-F1, entity F1): percentile bootstrap with ``B = 10,000``
  resamples from ``numpy.random.default_rng(2026)``, stratified by gold class or resampled by
  ticket (cluster), vectorized over resamples;
* paired comparisons: a same-index paired bootstrap of a difference, approximate
  randomization, and the McNemar exact and mid-p tests; Holm (and BH-FDR for labelled
  exploratory screens) over a family of p-values;
* seeds: per-seed values, mean, SD with its chi-square CI, range, and the two-level bootstrap
  of the seed mean.

The module is pure NumPy/SciPy: it never reads files or models. Every random draw comes from
a seeded ``numpy.random.Generator``, so a result is reproducible from ``(seed, n_resamples)``
and the data order. Two systems scored on the same records with the same seed see identical
resample indices, which is what the paired protocol requires.
"""

import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist
from typing import Final, Literal

import numpy as np
from numpy.typing import NDArray
from scipy import stats

B_DEFAULT: Final = 10_000
"""Bootstrap resamples (A-10; the spec's earlier 1,000 added avoidable Monte-Carlo error)."""
RNG_SEED: Final = 2026
"""Default ``numpy.random.default_rng`` seed, recorded in every report."""
LEVEL: Final = 0.95
CHUNK_ROWS: Final = 1_000
"""Resamples evaluated per vectorized chunk (bounds memory at n ~ 1,000 records)."""
_TIE_TOLERANCE: Final = 1e-12

type IntArray = NDArray[np.int64]
type FloatArray = NDArray[np.float64]
type RowStatistic = Callable[[IntArray], FloatArray]
"""Maps an ``(R, n)`` matrix of record indices to ``R`` statistic values."""
type PairMetric = Callable[[IntArray, IntArray], FloatArray]
"""Maps ``(R, n)`` gold and prediction label-code matrices to ``R`` metric values."""
Alternative = Literal["two-sided", "greater"]


@dataclass(frozen=True, slots=True)
class Interval:
    """A point estimate with its confidence interval.

    Attributes:
        point: Estimate (``None`` when undefined, e.g. ``n = 0``).
        low: Lower CI bound.
        high: Upper CI bound.
        method: How the interval was computed (``wilson``, ``clopper-pearson``,
            ``stratified-percentile-bootstrap``...).
        n: Units the estimate is based on (records, tickets, items).
        k: Successes, for proportions.
        level: Confidence level.
        n_resamples: Bootstrap resamples, for bootstrap intervals.
        rng_seed: Bootstrap seed, for bootstrap intervals.
    """

    point: float | None
    low: float | None
    high: float | None
    method: str
    n: int
    k: int | None = None
    level: float = LEVEL
    n_resamples: int | None = None
    rng_seed: int | None = None


def undefined(n: int = 0, *, level: float = LEVEL, reason: str = "n = 0") -> Interval:
    """An estimate that cannot be computed (reported, never silently dropped).

    Args:
        n: Units available.
        level: Confidence level.
        reason: Why it is undefined.

    Returns:
        An interval with ``None`` point and bounds.
    """
    return Interval(None, None, None, f"undefined ({reason})", n, level=level)


# --------------------------------------------------------------------------- proportions


def _check_level(level: float) -> None:
    if not 0 < level < 1:
        msg = "confidence level must be in (0, 1)"
        raise ValueError(msg)


def _check_counts(k: int, n: int) -> None:
    if n <= 0 or not 0 <= k <= n:
        msg = "need n > 0 and 0 <= k <= n"
        raise ValueError(msg)


def z_for(level: float = LEVEL) -> float:
    """Two-sided standard-normal quantile for a confidence level.

    Args:
        level: Confidence level (0.95 gives 1.959964).

    Returns:
        ``z`` such that ``P(|Z| <= z) = level``.
    """
    _check_level(level)
    return NormalDist().inv_cdf(1 - (1 - level) / 2)


def wilson_bounds(k: int, n: int, z: float) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, parameterized by ``z``.

    Args:
        k: Successes.
        n: Trials.
        z: Normal quantile (1.96 for 95%).

    Returns:
        ``(low, high)`` clipped to ``[0, 1]``.

    Raises:
        ValueError: If ``n`` is not positive or ``k`` is outside ``[0, n]``.
    """
    _check_counts(k, n)
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def wilson_interval(k: int, n: int, *, level: float = LEVEL) -> tuple[float, float]:
    """Wilson score interval (Brown, Cai & DasGupta 2001; Newcombe 1998 method 3).

    Args:
        k: Successes.
        n: Trials.
        level: Confidence level.

    Returns:
        ``(low, high)``.
    """
    return wilson_bounds(k, n, z_for(level))


def clopper_pearson_interval(k: int, n: int, *, level: float = LEVEL) -> tuple[float, float]:
    """Two-sided exact (Clopper-Pearson) interval.

    Args:
        k: Successes.
        n: Trials.
        level: Confidence level.

    Returns:
        ``(low, high)``; ``low = 0`` at ``k = 0`` and ``high = 1`` at ``k = n``.
    """
    _check_counts(k, n)
    _check_level(level)
    alpha = 1 - level
    low = 0.0 if k == 0 else float(stats.beta.ppf(alpha / 2, k, n - k + 1))
    high = 1.0 if k == n else float(stats.beta.ppf(1 - alpha / 2, k + 1, n - k))
    return low, high


def exact_lower_bound(k: int, n: int, *, level: float = LEVEL) -> float:
    """One-sided exact (Clopper-Pearson) lower confidence bound for a proportion.

    With every item a success (``k = n``) the bound is ``(1 - level) ** (1 / n)``, about
    ``1 - 3/n`` (the "rule of three"): M-07a publishes it next to its 1.00 point estimate.

    Args:
        k: Successes.
        n: Trials.
        level: One-sided confidence level.

    Returns:
        The lower bound.
    """
    _check_counts(k, n)
    _check_level(level)
    if k == 0:
        return 0.0
    if k == n:
        return float((1 - level) ** (1 / n))
    return float(stats.beta.ppf(1 - level, k, n - k + 1))


def proportion(k: int, n: int, *, level: float = LEVEL) -> Interval:
    """Proportion with the protocol's interval: Wilson, exact at ``k = 0`` or ``k = n``.

    Args:
        k: Successes.
        n: Trials (``0`` gives an undefined estimate).
        level: Confidence level.

    Returns:
        The estimate.
    """
    if n == 0:
        return undefined(level=level)
    if k in (0, n):
        low, high = clopper_pearson_interval(k, n, level=level)
        method = "clopper-pearson"
    else:
        low, high = wilson_interval(k, n, level=level)
        method = "wilson"
    return Interval(k / n, low, high, method, n, k, level)


# --------------------------------------------------------------------------- bootstrap


def resample_indices(
    n: int, n_resamples: int, rng: np.random.Generator, strata: IntArray | None = None
) -> IntArray:
    """Draw an ``(n_resamples, n)`` matrix of record indices with replacement.

    With ``strata``, column ``j`` always holds a member of record ``j``'s stratum, so every
    stratum keeps its size in every resample (the test sets are built with fixed per-class
    quotas, and no class can vanish from a resample).

    Args:
        n: Records.
        n_resamples: Rows to draw.
        rng: Seeded generator.
        strata: Optional stratum code per record (length ``n``).

    Returns:
        The index matrix.

    Raises:
        ValueError: If ``strata`` does not have length ``n``.
    """
    if strata is None:
        return rng.integers(0, n, size=(n_resamples, n), dtype=np.int64)
    codes = np.asarray(strata, dtype=np.int64)
    if codes.shape != (n,):
        msg = "strata must have one code per record"
        raise ValueError(msg)
    out = np.empty((n_resamples, n), dtype=np.int64)
    for value in np.unique(codes):
        members = np.flatnonzero(codes == value).astype(np.int64)
        picks = rng.integers(0, members.size, size=(n_resamples, members.size), dtype=np.int64)
        out[:, members] = members[picks]
    return out


def bootstrap_distribution(
    statistic: RowStatistic,
    n: int,
    *,
    strata: IntArray | None = None,
    n_resamples: int = B_DEFAULT,
    seed: int = RNG_SEED,
) -> FloatArray:
    """Evaluate a statistic on ``n_resamples`` bootstrap resamples (chunked, vectorized).

    Args:
        statistic: Row statistic over index matrices.
        n: Records.
        strata: Optional stratum per record.
        n_resamples: Resamples.
        seed: ``numpy.random.default_rng`` seed.

    Returns:
        One value per resample.

    Raises:
        ValueError: If ``n`` or ``n_resamples`` is not positive.
    """
    if n <= 0 or n_resamples <= 0:
        msg = "bootstrap needs n > 0 and n_resamples > 0"
        raise ValueError(msg)
    rng = np.random.default_rng(seed)
    parts: list[FloatArray] = []
    remaining = n_resamples
    while remaining > 0:
        rows = min(CHUNK_ROWS, remaining)
        values = statistic(resample_indices(n, rows, rng, strata))
        parts.append(np.asarray(values, dtype=np.float64))
        remaining -= rows
    return np.concatenate(parts)


def percentile_bounds(distribution: FloatArray, level: float = LEVEL) -> tuple[float, float]:
    """Percentile CI of a bootstrap distribution (non-finite values ignored).

    Args:
        distribution: Bootstrap values.
        level: Confidence level.

    Returns:
        ``(low, high)``; ``(nan, nan)`` when no value is finite.
    """
    _check_level(level)
    finite = distribution[np.isfinite(distribution)]
    if finite.size == 0:
        return math.nan, math.nan
    tail = (1 - level) / 2
    low, high = np.quantile(finite, [tail, 1 - tail])
    return float(low), float(high)


def identity_indices(n: int) -> IntArray:
    """The ``(1, n)`` index matrix of the original sample (the point estimate).

    Args:
        n: Records.

    Returns:
        ``[[0, 1, ..., n - 1]]``.
    """
    return np.arange(n, dtype=np.int64)[None, :]


def bootstrap(
    statistic: RowStatistic,
    n: int,
    *,
    strata: IntArray | None = None,
    n_resamples: int = B_DEFAULT,
    seed: int = RNG_SEED,
    level: float = LEVEL,
    label: str = "percentile-bootstrap",
) -> Interval:
    """Point estimate plus percentile bootstrap CI of a row statistic.

    Args:
        statistic: Row statistic over index matrices.
        n: Records (``0`` gives an undefined estimate).
        strata: Optional stratum per record (the method name gets a ``stratified-`` prefix).
        n_resamples: Resamples.
        seed: Generator seed.
        level: Confidence level.
        label: Method name.

    Returns:
        The estimate; ``point`` is ``None`` when the statistic is undefined on the sample.
    """
    if n == 0:
        return undefined(level=level)
    point = float(statistic(identity_indices(n))[0])
    distribution = bootstrap_distribution(
        statistic, n, strata=strata, n_resamples=n_resamples, seed=seed
    )
    low, high = percentile_bounds(distribution, level)
    method = f"stratified-{label}" if strata is not None else label
    return Interval(
        None if math.isnan(point) else point,
        None if math.isnan(low) else low,
        None if math.isnan(high) else high,
        method,
        n,
        level=level,
        n_resamples=n_resamples,
        rng_seed=seed,
    )


def paired_bootstrap(
    statistic_a: RowStatistic,
    statistic_b: RowStatistic,
    n: int,
    *,
    strata: IntArray | None = None,
    n_resamples: int = B_DEFAULT,
    seed: int = RNG_SEED,
    level: float = LEVEL,
) -> Interval:
    """CI of ``statistic_a - statistic_b``, both evaluated on identical resamples.

    Args:
        statistic_a: Statistic of system A.
        statistic_b: Statistic of system B (same records, same order).
        n: Records.
        strata: Optional stratum per record.
        n_resamples: Resamples.
        seed: Generator seed.
        level: Confidence level.

    Returns:
        The difference estimate.
    """

    def difference(indices: IntArray) -> FloatArray:
        return statistic_a(indices) - statistic_b(indices)

    return bootstrap(
        difference,
        n,
        strata=strata,
        n_resamples=n_resamples,
        seed=seed,
        level=level,
        label="paired-percentile-bootstrap",
    )


def seed_mean_bootstrap(
    statistics: Sequence[RowStatistic],
    n: int,
    *,
    strata: IntArray | None = None,
    n_resamples: int = B_DEFAULT,
    seed: int = RNG_SEED,
    level: float = LEVEL,
) -> Interval:
    """Two-level bootstrap of a seed mean (ERPROT D4).

    Each resample of the test records is scored by every seed's predictions, and the seed
    values are averaged; the percentile CI of those averages is the headline E2/E4 interval.

    Args:
        statistics: One row statistic per seed (same records, same order).
        n: Records.
        strata: Optional stratum per record.
        n_resamples: Resamples.
        seed: Generator seed.
        level: Confidence level.

    Returns:
        The seed-mean estimate.

    Raises:
        ValueError: If no seed is given.
    """
    if not statistics:
        msg = "seed_mean_bootstrap needs at least one seed"
        raise ValueError(msg)

    def mean_over_seeds(indices: IntArray) -> FloatArray:
        stacked = np.stack([np.asarray(s(indices), dtype=np.float64) for s in statistics])
        return np.asarray(stacked.mean(axis=0), dtype=np.float64)

    return bootstrap(
        mean_over_seeds,
        n,
        strata=strata,
        n_resamples=n_resamples,
        seed=seed,
        level=level,
        label="two-level-percentile-bootstrap",
    )


# --------------------------------------------------------------------------- vectorized metrics


def encode(values: Sequence[str], vocabulary: Sequence[str]) -> IntArray:
    """Map labels to integer codes.

    Args:
        values: Labels.
        vocabulary: Ordered label set (every value must be a member).

    Returns:
        Codes in vocabulary order.

    Raises:
        ValueError: If a value is not in the vocabulary.
    """
    index = {label: code for code, label in enumerate(vocabulary)}
    try:
        return np.fromiter((index[v] for v in values), dtype=np.int64, count=len(values))
    except KeyError as exc:
        msg = f"label {exc.args[0]!r} is not in the vocabulary"
        raise ValueError(msg) from None


def confusion_counts(gold: IntArray, pred: IntArray, n_classes: int) -> NDArray[np.int64]:
    """Row-wise confusion matrices ``cm[r, gold, pred]`` via one ``bincount``.

    Args:
        gold: ``(R, n)`` or ``(n,)`` gold codes.
        pred: Same shape, predicted codes.
        n_classes: Vocabulary size.

    Returns:
        ``(R, n_classes, n_classes)`` counts.
    """
    gold2 = np.atleast_2d(np.asarray(gold, dtype=np.int64))
    pred2 = np.atleast_2d(np.asarray(pred, dtype=np.int64))
    rows = gold2.shape[0]
    offsets = (np.arange(rows, dtype=np.int64) * n_classes * n_classes)[:, None]
    codes = gold2 * n_classes + pred2 + offsets
    counts = np.bincount(codes.ravel(), minlength=rows * n_classes * n_classes)
    return counts.reshape(rows, n_classes, n_classes).astype(np.int64)


def macro_f1_rows(gold: IntArray, pred: IntArray, n_classes: int, labels: IntArray) -> FloatArray:
    """Row-wise macro-F1 over ``labels``.

    Equals ``sklearn.metrics.f1_score(labels=labels, average="macro", zero_division=0)`` per
    row: a label with no gold item and no prediction scores 0 and still counts in the mean.

    Args:
        gold: ``(R, n)`` or ``(n,)`` gold codes.
        pred: Same shape, predicted codes (may include codes outside ``labels``).
        n_classes: Vocabulary size.
        labels: Codes averaged over.

    Returns:
        ``R`` macro-F1 values.
    """
    cm = confusion_counts(gold, pred, n_classes)
    tp = np.einsum("rii->ri", cm).astype(np.float64)
    fp = cm.sum(axis=1).astype(np.float64) - tp
    fn = cm.sum(axis=2).astype(np.float64) - tp
    denominator = 2 * tp + fp + fn
    f1 = np.divide(2 * tp, denominator, out=np.zeros_like(denominator), where=denominator > 0)
    return np.asarray(f1[:, np.asarray(labels, dtype=np.int64)].mean(axis=1), dtype=np.float64)


def accuracy_rows(gold: IntArray, pred: IntArray) -> FloatArray:
    """Row-wise accuracy.

    Args:
        gold: ``(R, n)`` gold codes.
        pred: Same shape, predicted codes.

    Returns:
        ``R`` accuracies.
    """
    equal = np.atleast_2d(np.asarray(gold) == np.asarray(pred))
    return np.asarray(equal.mean(axis=1), dtype=np.float64)


def micro_f1_rows(counts: NDArray[np.int64], indices: IntArray) -> FloatArray:
    """Micro-F1 of per-unit ``(tp, fp, fn)`` counts over resampled units (cluster bootstrap).

    Args:
        counts: ``(n, 3)`` per-ticket true positives, false positives, false negatives.
        indices: ``(R, n)`` resampled ticket indices.

    Returns:
        ``R`` values of ``2 TP / (2 TP + FP + FN)`` (``nan`` when the denominator is 0).
    """
    totals = counts[indices].sum(axis=1).astype(np.float64)
    tp, fp, fn = totals[:, 0], totals[:, 1], totals[:, 2]
    denominator = 2 * tp + fp + fn
    return np.divide(
        2 * tp, denominator, out=np.full_like(denominator, np.nan), where=denominator > 0
    )


# --------------------------------------------------------------------------- paired tests


def randomization_pvalue(
    gold: IntArray,
    pred_a: IntArray,
    pred_b: IntArray,
    metric: PairMetric,
    *,
    n_resamples: int = B_DEFAULT,
    seed: int = RNG_SEED,
    alternative: Alternative = "two-sided",
) -> float:
    """Approximate-randomization p-value for ``metric(A) - metric(B)`` (paired).

    Each resample swaps every item's pair of predictions with probability 1/2; the p-value is
    ``(1 + #extreme) / (1 + R)`` (ties within 1e-12 count as extreme).

    Args:
        gold: ``(n,)`` gold codes.
        pred_a: ``(n,)`` codes of system A.
        pred_b: ``(n,)`` codes of system B.
        metric: Metric over ``(R, n)`` gold and prediction matrices.
        n_resamples: Randomization rounds.
        seed: Generator seed.
        alternative: ``greater`` tests A > B; ``two-sided`` tests A != B.

    Returns:
        The p-value in ``(0, 1]``.

    Raises:
        ValueError: If the arrays differ in shape or are empty.
    """
    g = np.asarray(gold, dtype=np.int64)
    a = np.asarray(pred_a, dtype=np.int64)
    b = np.asarray(pred_b, dtype=np.int64)
    if g.ndim != 1 or g.size == 0 or a.shape != g.shape or b.shape != g.shape:
        msg = "randomization needs equally long, non-empty 1-D code arrays"
        raise ValueError(msg)
    observed = float(metric(g[None, :], a[None, :])[0] - metric(g[None, :], b[None, :])[0])
    rng = np.random.default_rng(seed)
    extreme = 0
    remaining = n_resamples
    while remaining > 0:
        rows = min(CHUNK_ROWS, remaining)
        swap = rng.random((rows, g.size)) < 0.5  # noqa: PLR2004 - fair coin per item
        tiled = np.broadcast_to(g, (rows, g.size))
        null = metric(tiled, np.where(swap, b, a)) - metric(tiled, np.where(swap, a, b))
        if alternative == "greater":
            extreme += int(np.sum(null >= observed - _TIE_TOLERANCE))
        else:
            extreme += int(np.sum(np.abs(null) >= abs(observed) - _TIE_TOLERANCE))
        remaining -= rows
    return (1 + extreme) / (1 + n_resamples)


@dataclass(frozen=True, slots=True)
class McNemarResult:
    """McNemar test on paired binary outcomes.

    Attributes:
        n10: Items where A is correct and B is wrong.
        n01: Items where A is wrong and B is correct.
        p_exact: Two-sided exact conditional (binomial) p-value.
        p_midp: Two-sided mid-p value (Fagerland et al. 2013; the protocol's primary McNemar).
        chi2: Uncorrected chi-square statistic (``None`` without discordant pairs).
        p_chi2: Its asymptotic p-value.
    """

    n10: int
    n01: int
    p_exact: float
    p_midp: float
    chi2: float | None
    p_chi2: float | None


def mcnemar(correct_a: Sequence[bool], correct_b: Sequence[bool]) -> McNemarResult:
    """McNemar exact and mid-p tests on per-item correctness of two systems.

    Args:
        correct_a: Correctness of system A per item.
        correct_b: Correctness of system B per item (same items, same order).

    Returns:
        The discordant counts and p-values (1.0 when there is no discordant pair).

    Raises:
        ValueError: If the sequences differ in length.
    """
    a = np.asarray(correct_a, dtype=bool)
    b = np.asarray(correct_b, dtype=bool)
    if a.shape != b.shape:
        msg = "McNemar needs paired outcomes of equal length"
        raise ValueError(msg)
    n10 = int(np.sum(a & ~b))
    n01 = int(np.sum(~a & b))
    discordant = n10 + n01
    if discordant == 0:
        return McNemarResult(n10, n01, 1.0, 1.0, None, None)
    smaller = min(n10, n01)
    cdf = float(stats.binom.cdf(smaller, discordant, 0.5))
    pmf = float(stats.binom.pmf(smaller, discordant, 0.5))
    chi2 = (n10 - n01) ** 2 / discordant
    return McNemarResult(
        n10,
        n01,
        min(1.0, 2 * cdf),
        min(1.0, 2 * cdf - pmf),
        chi2,
        float(stats.chi2.sf(chi2, 1)),
    )


def _check_pvalues(pvalues: Sequence[float]) -> list[float]:
    values = [float(p) for p in pvalues]
    if any(math.isnan(p) or not 0 <= p <= 1 for p in values):
        msg = "p-values must lie in [0, 1]"
        raise ValueError(msg)
    return values


def holm(pvalues: Sequence[float], *, alpha: float = 0.05) -> tuple[list[float], list[bool]]:
    """Holm step-down adjustment (family-wise error rate).

    Args:
        pvalues: Raw p-values of one pre-registered family.
        alpha: Family-wise level.

    Returns:
        ``(adjusted, reject)`` in the input order.
    """
    values = _check_pvalues(pvalues)
    m = len(values)
    order = sorted(range(m), key=lambda i: (values[i], i))
    adjusted = [0.0] * m
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * values[index]))
        adjusted[index] = running
    return adjusted, [p <= alpha for p in adjusted]


def benjamini_hochberg(pvalues: Sequence[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values (FDR; exploratory screens only, labelled as such).

    Args:
        pvalues: Raw p-values.

    Returns:
        Adjusted p-values in the input order.
    """
    values = _check_pvalues(pvalues)
    m = len(values)
    order = sorted(range(m), key=lambda i: (values[i], i), reverse=True)
    adjusted = [0.0] * m
    running = 1.0
    for position, index in enumerate(order):
        rank = m - position
        running = min(running, values[index] * m / rank)
        adjusted[index] = running
    return adjusted


# --------------------------------------------------------------------------- seeds


@dataclass(frozen=True, slots=True)
class SeedSummary:
    """Across-seed aggregate of one metric (ERPROT D4; never "best of 3 on test").

    Attributes:
        per_seed: Seed label to value, in input order.
        mean: Mean over seeds.
        sd: Sample SD (``ddof=1``; ``None`` for a single seed).
        sd_low: Lower chi-square CI bound of the SD (normal theory).
        sd_high: Upper chi-square CI bound of the SD.
        minimum: Smallest seed value.
        maximum: Largest seed value.
        level: Confidence level of the SD interval.
    """

    per_seed: Mapping[str, float]
    mean: float
    sd: float | None
    sd_low: float | None
    sd_high: float | None
    minimum: float
    maximum: float
    level: float = LEVEL

    @property
    def n_seeds(self) -> int:
        """Number of seeds aggregated."""
        return len(self.per_seed)


def seed_summary(per_seed: Mapping[str, float], *, level: float = LEVEL) -> SeedSummary:
    """Mean, SD with its chi-square CI and range of per-seed values.

    With three seeds the 95% CI of the SD is ``[0.521 s, 6.285 s]``: the SD itself is barely
    identified, which is why every seed's value is published.

    Args:
        per_seed: Seed label to metric value.
        level: Confidence level of the SD interval.

    Returns:
        The summary.

    Raises:
        ValueError: If no seed is given.
    """
    if not per_seed:
        msg = "seed_summary needs at least one seed"
        raise ValueError(msg)
    _check_level(level)
    values = np.asarray(list(per_seed.values()), dtype=np.float64)
    mean = float(values.mean())
    if values.size < 2:  # noqa: PLR2004 - an SD needs two values
        return SeedSummary(dict(per_seed), mean, None, None, None, mean, mean, level)
    sd = float(values.std(ddof=1))
    dof = values.size - 1
    tail = (1 - level) / 2
    sd_low = sd * math.sqrt(dof / float(stats.chi2.ppf(1 - tail, dof)))
    sd_high = sd * math.sqrt(dof / float(stats.chi2.ppf(tail, dof)))
    return SeedSummary(
        dict(per_seed),
        mean,
        sd,
        sd_low,
        sd_high,
        float(values.min()),
        float(values.max()),
        level,
    )


# --------------------------------------------------------------------------- agreement


def cohen_kappa(first: Sequence[str], second: Sequence[str]) -> float:
    """Cohen's kappa for two raters on nominal labels.

    Args:
        first: Labels of rater 1.
        second: Labels of rater 2 (same items, same order).

    Returns:
        Kappa; ``nan`` when chance agreement is 1 (every label identical and constant).

    Raises:
        ValueError: If the sequences differ in length or are empty.
    """
    if len(first) != len(second) or not first:
        msg = "kappa needs two equally long, non-empty label sequences"
        raise ValueError(msg)
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / n
    left, right = Counter(first), Counter(second)
    expected = sum(left[label] * right[label] for label in left) / (n * n)
    if math.isclose(expected, 1.0):
        return math.nan
    return (observed - expected) / (1 - expected)
