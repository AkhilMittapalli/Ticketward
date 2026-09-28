"""Repository paths used by the P1 data tools.

The ml project never imports the backend. Everything it shares with the backend is a file
in the repository (the exported JSON Schemas in ``schemas/json/``), so the tools locate the
repository root first. ``TW_REPO_ROOT`` overrides the search (useful on Colab/Kaggle when
the package is installed from a checkout elsewhere).
"""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT_ENV = "TW_REPO_ROOT"
_MARKER = Path("schemas") / "json" / "taxonomy.schema.json"


class RepoNotFoundError(RuntimeError):
    """Raised when the repository root (with ``schemas/json``) cannot be located."""


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the repository root.

    Args:
        start: Directory to search upwards from (defaults to this file's directory).

    Returns:
        The first ancestor that contains ``schemas/json/taxonomy.schema.json``, or the
        directory named by ``TW_REPO_ROOT`` when that variable is set.

    Raises:
        RepoNotFoundError: If no ancestor holds the exported contracts.
    """
    override = os.environ.get(REPO_ROOT_ENV)
    if override:
        root = Path(override).resolve()
        if not (root / _MARKER).is_file():
            msg = f"{REPO_ROOT_ENV} does not point at a repository with {_MARKER.as_posix()}"
            raise RepoNotFoundError(msg)
        return root
    here = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (here, *here.parents):
        if (candidate / _MARKER).is_file():
            return candidate
    msg = f"no ancestor of {here} contains {_MARKER.as_posix()}; set {REPO_ROOT_ENV}"
    raise RepoNotFoundError(msg)


@dataclass(frozen=True, slots=True)
class RepoPaths:
    """Well-known locations inside the repository.

    Attributes:
        root: Repository root.
    """

    root: Path

    @property
    def schemas_dir(self) -> Path:
        """Exported JSON Schemas (the only contract shared with the backend)."""
        return self.root / "schemas" / "json"

    @property
    def spec_dir(self) -> Path:
        """Generation specs: matrix, fact sheet, pools, mappings, protected strings."""
        return self.root / "data" / "spec"

    @property
    def pools_dir(self) -> Path:
        """Split-disjoint persona/company/entity pools."""
        return self.spec_dir / "pools"

    @property
    def generated_dir(self) -> Path:
        """Generated datasets (gitignored; published privately on the HF Hub)."""
        return self.root / "data" / "generated"

    @property
    def manifests_dir(self) -> Path:
        """Content-hash manifests (committed)."""
        return self.root / "data" / "manifests"

    @property
    def kb_dir(self) -> Path:
        """Knowledge-base markdown sources (written later in P1)."""
        return self.root / "data" / "kb"

    @property
    def prompts_dir(self) -> Path:
        """Versioned generator prompt families."""
        return self.root / "ml" / "prompts" / "datagen"

    @property
    def configs_dir(self) -> Path:
        """Versioned ml configs (prices, provider settings, leakage)."""
        return self.root / "ml" / "configs"

    @property
    def hard_set_file(self) -> Path:
        """Owner-written hard set (spec §14.1)."""
        return self.root / "evals" / "hard_set.v1.jsonl"

    @property
    def hard_dev_gold_file(self) -> Path:
        """Open ``hard_dev`` gold rows, written when the split is frozen (spec §9.12 D6-7)."""
        return self.root / "evals" / "hard_dev.v1.jsonl"

    @property
    def ood_dir(self) -> Path:
        """Bitext OOD pointers and owner review decisions."""
        return self.root / "evals" / "ood"

    @property
    def reports_dir(self) -> Path:
        """Committed evaluation and leakage reports."""
        return self.root / "evals" / "reports"

    @property
    def evals_dir(self) -> Path:
        """Evaluation data, reports, the access log and the pre-registration (``evals/``)."""
        return self.root / "evals"

    @property
    def analysis_plan_file(self) -> Path:
        """Pre-registered analysis plan (hashed into every report as ``analysis_plan_sha``)."""
        return self.evals_dir / "ANALYSIS_PLAN.md"

    @property
    def sealed_access_log(self) -> Path:
        """Append-only log of every sealed-split evaluation (``tw_ml.eval.holdout``)."""
        return self.evals_dir / "sealed_access.jsonl"

    @property
    def lexicons_dir(self) -> Path:
        """Policy lexicons (data files shared by the P6 engine and the E1 rules baseline)."""
        return self.root / "backend" / "policy" / "lexicons"


def default_paths() -> RepoPaths:
    """Paths for the repository this package lives in.

    Returns:
        A ``RepoPaths`` rooted at :func:`find_repo_root`.
    """
    return RepoPaths(find_repo_root())
