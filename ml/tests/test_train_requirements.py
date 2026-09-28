"""The notebook install file is the hashed export of ml/uv.lock, minus torch (P3.7, A-03).

``ml/requirements/train.txt`` is regenerated with the command in its header (``uv export ...
--prune torch``). These tests fail when it drifts from the lock (versions, hashes or the
package set), when a pin of spec §9.5 changes, or when torch/CUDA wheels would be installed.
"""

import re
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from tw_ml.datagen.paths import RepoPaths

EXPORT_COMMAND = (
    "uv export --frozen --no-emit-project --extra train --no-default-groups --group eval "
    "--format requirements-txt --prune torch --output-file requirements/train.txt"
)
PINS = {
    "trl": "1.14.0",
    "transformers": "5.17.0",
    "peft": "0.21.0",
    "accelerate": "1.15.0",
    "bitsandbytes": "0.50.2",
}
PURE_PYTHON_NVIDIA = frozenset({"nvidia-ml-py"})
"""NVML bindings that codecarbon imports (no CUDA runtime); every other nvidia-* is refused."""
_REQUIREMENT = re.compile(r"^(?P<name>[a-z0-9._-]+)==(?P<version>[^\s;\\]+)(?P<marker>\s*;[^\\]*)?")
_HASH = re.compile(r"--hash=sha256:(?P<hash>[0-9a-f]{64})")


def _exported(path: Path) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _REQUIREMENT.match(line)
        if match:
            current = {
                "version": match["version"],
                "marker": (match["marker"] or "").strip(" ;"),
                "hashes": set(),
            }
            entries[match["name"]] = current
            continue
        found = _HASH.search(line)
        if found and current is not None:
            current["hashes"].add(found["hash"])
    return entries


@pytest.fixture(scope="module")
def lock(paths: RepoPaths) -> dict[str, dict[str, Any]]:
    document = tomllib.loads((paths.root / "ml" / "uv.lock").read_text(encoding="utf-8"))
    return {package["name"]: package for package in document["package"]}


@pytest.fixture(scope="module")
def exported(paths: RepoPaths) -> dict[str, dict[str, Any]]:
    return _exported(paths.root / "ml" / "requirements" / "train.txt")


def _hashes(package: dict[str, Any]) -> set[str]:
    artifacts = [*package.get("wheels", []), *([package["sdist"]] if "sdist" in package else [])]
    return {artifact["hash"].removeprefix("sha256:") for artifact in artifacts}


def _closure(lock: dict[str, dict[str, Any]], start: Iterable[dict[str, Any]]) -> set[str]:
    """Package names reachable from ``start`` in the lock graph, never through torch."""
    seen: set[str] = set()
    stack = list(start)
    while stack:
        dependency = stack.pop()
        name = dependency["name"]
        package = lock[name]
        for extra in dependency.get("extra", []):
            stack.extend(package.get("optional-dependencies", {}).get(extra, []))
        if name in seen or name == "torch":
            continue
        seen.add(name)
        stack.extend(package.get("dependencies", []))
    return seen


def test_header_names_the_regeneration_command(paths: RepoPaths) -> None:
    header = (paths.root / "ml" / "requirements" / "train.txt").read_text(encoding="utf-8")
    assert EXPORT_COMMAND in header.splitlines()[1]


def test_export_matches_the_lock(
    lock: dict[str, dict[str, Any]], exported: dict[str, dict[str, Any]]
) -> None:
    root = lock["tw-ml"]
    start = [
        *root["dependencies"],
        *root["optional-dependencies"]["train"],
        *root["dev-dependencies"]["eval"],
    ]
    assert set(exported) == _closure(lock, start)
    for name, entry in exported.items():
        assert entry["version"] == lock[name]["version"], name
        assert entry["hashes"], f"{name} has no hash (pip --require-hashes)"
        assert entry["hashes"] <= _hashes(lock[name]), f"{name} hashes are not the lock's"


def test_no_torch_or_cuda_runtime_wheels(
    lock: dict[str, dict[str, Any]], exported: dict[str, dict[str, Any]]
) -> None:
    forbidden = {n for n in exported if n in {"torch", "triton"} or n.startswith("nvidia-")}
    assert forbidden <= PURE_PYTHON_NVIDIA
    assert "wheels" not in lock["torch"]  # the override keeps torch artifact-free in the lock
    assert "sdist" not in lock["torch"]
    assert not any(
        n == "triton" or (n.startswith("nvidia-") and n not in PURE_PYTHON_NVIDIA) for n in lock
    )


def test_spec_pins(exported: dict[str, dict[str, Any]]) -> None:
    for name, version in PINS.items():
        assert exported[name]["version"] == version, name
    assert exported["bitsandbytes"]["marker"] == "sys_platform == 'linux'"
    assert tuple(int(p) for p in exported["datasets"]["version"].split(".")[:2]) >= (4, 7)
    assert int(exported["huggingface-hub"]["version"].split(".")[0]) < 2
    assert {"mlflow", "codecarbon", "numpy", "scipy", "pydantic", "pyyaml", "httpx"} <= set(
        exported
    )


def test_pyproject_train_extra(paths: RepoPaths) -> None:
    project = tomllib.loads((paths.root / "ml" / "pyproject.toml").read_text(encoding="utf-8"))
    extra = project["project"]["optional-dependencies"]["train"]
    for name, version in PINS.items():
        assert any(r.startswith(f"{name}=={version}") for r in extra), name
    assert "huggingface-hub<2" in extra
    assert "datasets>=4.7.0" in extra
    assert not any(r.startswith("torch") for r in extra)
    assert "train" not in project["dependency-groups"]  # the extra replaced the planned group
    assert "httpx>=0.28" in project["dependency-groups"]["eval"]
    assert project["tool"]["uv"]["override-dependencies"] == ["torch; sys_platform == 'never'"]
    assert "train" not in project["tool"]["uv"]["default-groups"]
