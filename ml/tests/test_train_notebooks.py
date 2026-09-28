"""The Kaggle and Colab notebooks stay thin, output-free and secret-free (P2.10, spec §9.5).

Every command a notebook runs must be ``python -m tw_ml.train...``, one of the two pinned
installs, or the git clone/checkout of the pinned commit; the token only ever moves from the
platform's secret store into the environment.
"""

import ast
import re
from pathlib import Path
from typing import Any

import pytest

from tw_ml.datagen.paths import RepoPaths

nbformat = pytest.importorskip("nbformat")

NOTEBOOKS = ("train_kaggle.ipynb", "train_colab.ipynb")
PIP_INSTALLS = (
    (
        "-m",
        "pip",
        "install",
        "--quiet",
        "--no-deps",
        "--require-hashes",
        "-r",
        "ml/requirements/train.txt",
    ),
    ("-m", "pip", "install", "--quiet", "--no-deps", "-e", "./ml"),
)
GIT_COMMANDS = (
    ("git", "clone"),
    ("git", "-C", "ticketward", "checkout"),
    ("git", "-C", "ticketward", "rev-parse"),
)
TOKEN_LIKE = re.compile(
    r"hf_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}"
)
SECRET_SOURCES = {
    "train_kaggle.ipynb": 'os.environ["HF_TOKEN"] = UserSecretsClient().get_secret("HF_TOKEN")',
    "train_colab.ipynb": 'os.environ["HF_TOKEN"] = userdata.get("HF_TOKEN")',
}


def _load(paths: RepoPaths, name: str) -> Any:
    return nbformat.read(paths.root / "ml" / "notebooks" / name, as_version=4)


def _code(notebook: Any) -> list[str]:
    return [cell.source for cell in notebook.cells if cell.cell_type == "code"]


def _argv_prefix(node: ast.List) -> tuple[str, ...]:
    """Leading constant strings of an argv list (``sys.executable`` becomes ``python``)."""
    prefix: list[str] = []
    for element in node.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            prefix.append(element.value)
        elif isinstance(element, ast.Attribute) and ast.unparse(element) == "sys.executable":
            prefix.append("python")
        else:
            break
    return tuple(prefix)


def _commands(notebook: Any) -> list[tuple[str, ...]]:
    commands = []
    for source in _code(notebook):
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and ast.unparse(node.func) in {
                "subprocess.run",
                "subprocess.Popen",
            }:
                assert node.args, "subprocess calls take an argv list"
                argv = node.args[0]
                assert isinstance(argv, ast.List), "argv must be a literal list (no shell strings)"
                commands.append(_argv_prefix(argv))
                assert not any(k.arg == "shell" for k in node.keywords), "no shell=True"
    return commands


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_notebooks_are_valid_and_output_free(paths: RepoPaths, name: str) -> None:
    notebook = _load(paths, name)
    nbformat.validate(notebook)
    assert (notebook.nbformat, notebook.nbformat_minor) == (4, 5)
    assert notebook.cells[0].cell_type == "markdown"
    for cell in notebook.cells:
        if cell.cell_type == "code":
            assert cell.outputs == []
            assert cell.execution_count is None
    assert "widgets" not in notebook.metadata


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_notebooks_run_only_tw_ml_train_or_pinned_installs(paths: RepoPaths, name: str) -> None:
    commands = _commands(_load(paths, name))
    assert commands
    for command in commands:
        if command[:1] == ("git",):
            assert any(command[: len(g)] == g for g in GIT_COMMANDS), command
        elif command[1:4] == ("-m", "pip", "install"):
            assert command[1:] in PIP_INSTALLS, command
        else:
            assert command[:2] == ("python", "-m"), command
            assert command[2] == "tw_ml.train" or command[2].startswith("tw_ml.train."), command
    modules = {c[2] for c in commands if c[:2] == ("python", "-m")}
    assert {"tw_ml.train", "tw_ml.train.smoke", "tw_ml.train.hub", "pip"} <= modules
    for source in _code(_load(paths, name)):
        assert not any(line.lstrip().startswith(("!", "%")) for line in source.splitlines()), (
            "no shell magics"
        )


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_the_token_is_never_printed_or_committed(paths: RepoPaths, name: str) -> None:
    text = (paths.root / "ml" / "notebooks" / name).read_text(encoding="utf-8")
    assert not TOKEN_LIKE.search(text)
    sources = _code(_load(paths, name))
    token_lines = [line for source in sources for line in source.splitlines() if "HF_TOKEN" in line]
    assert SECRET_SOURCES[name] in token_lines
    for line in token_lines:
        assert not re.search(r"\b(print|display|logging|log\.|sys\.stdout|echo)\b", line), line
    # The secret is read exactly once, straight into the environment (never a Python variable).
    reads = [
        line.strip()
        for source in sources
        for line in source.splitlines()
        if "get_secret(" in line or "userdata.get(" in line
    ]
    assert reads == [SECRET_SOURCES[name]]


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_parameters_pin_the_commit_and_the_dataset(paths: RepoPaths, name: str) -> None:
    sources = _code(_load(paths, name))
    parameters, clone = sources[0], sources[1]
    assert 'REPO_URL = "https://github.com/AkhilMittapalli/Ticketward"' in parameters
    for name_ in ("GIT_SHA", "CONFIG", "HF_DATASET_ID", "HF_DATASET_REVISION", "EXPECTED_TORCH"):
        assert re.search(rf"^{name_} = ", parameters, re.MULTILINE), name_
    assert 'fullmatch(r"[0-9a-f]{40}", GIT_SHA)' in clone
    assert 'fullmatch(r"[0-9a-f]{40}", HF_DATASET_REVISION)' in clone
    assert "assert head == GIT_SHA" in clone
    joined = "\n".join(sources)
    assert "CUDA_VISIBLE_DEVICES" in joined
    assert "torch.__version__" in joined


def test_kaggle_runs_two_seeds_in_parallel_then_the_third(paths: RepoPaths) -> None:
    joined = "\n".join(_code(_load(paths, "train_kaggle.ipynb")))
    assert "PARALLEL_SEEDS = (42, 1337)" in joined
    assert "LAST_SEED = 2026" in joined
    assert "enumerate(PARALLEL_SEEDS)" in joined
    assert "GPU_COUNT = 2" in joined


def test_committed_notebook_files_have_lf_and_no_metadata_noise(paths: RepoPaths) -> None:
    for name in NOTEBOOKS:
        raw = (paths.root / "ml" / "notebooks" / name).read_bytes()
        assert b"\r\n" not in raw
        assert b'"execution_count": null' in raw
        assert b"output_type" not in raw
        assert Path(name).suffix == ".ipynb"
