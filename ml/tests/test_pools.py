"""Pools: split-disjoint, invented, seeded, brand-screened (spec §9.1.1, ERPROT D3)."""

from pathlib import Path

import pytest

from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.pools import (
    DEFAULT_POOL_SEED,
    POOL_NAMES,
    POOL_SIZES,
    PoolError,
    PoolSize,
    build_pools,
    is_denied,
    load_denylist,
    load_pools,
    write_pools,
)


def test_committed_pools_are_up_to_date(paths: RepoPaths) -> None:
    pools = build_pools(
        DEFAULT_POOL_SEED, denylist=load_denylist(paths.pools_dir / "brand_denylist.txt")
    )
    assert write_pools(paths.pools_dir, pools, DEFAULT_POOL_SEED, check=True) == []


def test_pools_are_deterministic_and_sized(paths: RepoPaths) -> None:
    denylist = load_denylist(paths.pools_dir / "brand_denylist.txt")
    first = build_pools(DEFAULT_POOL_SEED, denylist=denylist)
    assert first == build_pools(DEFAULT_POOL_SEED, denylist=denylist)
    assert first != build_pools(DEFAULT_POOL_SEED + 1, denylist=denylist)
    for name in POOL_NAMES:
        size = POOL_SIZES[name]
        pool = first[name]
        assert len(pool.personas) == size.personas
        assert len(pool.companies) == size.companies
        assert len(pool.competitors) == size.competitors
        assert len(pool.injections) == size.injections


def test_pools_share_nothing_across_splits(paths: RepoPaths) -> None:
    pools = build_pools(
        DEFAULT_POOL_SEED, denylist=load_denylist(paths.pools_dir / "brand_denylist.txt")
    )
    seen: dict[str, set[str]] = {}
    for name in POOL_NAMES:
        pool = pools[name]
        values = {
            *(p.full_name for p in pool.personas),
            *(p.persona_id for p in pool.personas),
            *(c.name.split()[0] for c in pool.companies),
            *(c.company_id for c in pool.companies),
            *(c.account_id for c in pool.companies),
            *(w for c in pool.companies for w in c.workspace_ids),
            *pool.competitors,
            *pool.injections,
            *{c.invoice_prefix for c in pool.companies},
        }
        for other, other_values in seen.items():
            assert not values & other_values, (name, other)
        seen[name] = values


def test_pool_names_avoid_brands_and_stay_plausible(paths: RepoPaths) -> None:
    denylist = load_denylist(paths.pools_dir / "brand_denylist.txt")
    assert "asana" in denylist
    assert "taskmoor" in denylist
    pools = build_pools(DEFAULT_POOL_SEED, denylist=denylist)
    limits = {"free": 5, "starter": 50, "business": 500}
    for pool in pools.values():
        for company in pool.companies:
            assert not is_denied(company.name, denylist)
            assert company.seats <= limits.get(company.plan, 10**6)
        assert not any(is_denied(name, denylist) for name in pool.competitors)
        assert {c.plan for c in pool.companies} == {"free", "starter", "business", "enterprise"}


def test_denylist_matching() -> None:
    denylist = ("asana", "ibm")
    assert is_denied("Asanaworks Labs", denylist)
    assert is_denied("IBM Foods", denylist)
    assert not is_denied("Fibmar Foods", denylist)  # short brands match whole words only
    pools = build_pools(DEFAULT_POOL_SEED, denylist=("brenvik",))
    assert all("brenvik" not in c.name.lower() for p in pools.values() for c in p.companies)


def test_loading_round_trips_and_lookups(paths: RepoPaths) -> None:
    val = load_pools("val", paths.pools_dir)
    assert val.persona(val.personas[3].persona_id) == val.personas[3]
    assert val.company(val.companies[2].company_id) == val.companies[2]
    with pytest.raises(KeyError):
        val.persona("p_zz_0000")
    with pytest.raises(KeyError):
        val.company("c_zz_0000")
    with pytest.raises(PoolError):
        load_pools("val", Path("does-not-exist"))


def test_small_name_spaces_fail_loudly() -> None:
    huge = {
        name: PoolSize(personas=10**6, companies=1, competitors=1, injections=1)
        for name in POOL_NAMES
    }
    with pytest.raises(PoolError, match="persona names"):
        build_pools(DEFAULT_POOL_SEED, sizes=huge)


def test_write_pools_writes_and_reports(tmp_path: Path) -> None:
    pools = build_pools(DEFAULT_POOL_SEED)
    written = write_pools(tmp_path, pools, DEFAULT_POOL_SEED, check=False)
    assert (tmp_path / "pools.json").is_file()
    assert len(written) == 4 * 4 + 1
    assert write_pools(tmp_path, pools, DEFAULT_POOL_SEED, check=True) == []
