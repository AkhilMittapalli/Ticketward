"""``python -m tw_ml.datagen <command>``: the P1 data tools.

Commands::

    plan      --split train                      quotas, strata, coverage, marginals of a plan
    pools     [--check]                          build (or check) data/spec/pools
    generate  --split train --family A --n 50 [--dry-run] [--budget-usd 5] [--host groq]
    validate  --split train [--file F]           schema + rule-checker + provenance report
    leakage   [--input train=F ...]              C1-C7 report (exit 1 when the gate fails)
    qa        sample | score | kappa             540-record audit, Wilson rule, Cohen's kappa
    manifest  build | freeze | verify            content-hash manifests (data/manifests)
    hardset   validate | split                   owner-written hard set checks and 30/70 split
    bitext    build | materialize --allow-download   Bitext OOD pointers (owner-run only)

Exit codes: 0 success, 1 a check failed, 2 usage or configuration error.
"""

import argparse
import getpass
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from tw_ml.datagen import generate as gen
from tw_ml.datagen import hardset, keys, leakage, manifest, qa
from tw_ml.datagen.bitext import HFRowSource, build_ood, load_mapping, materialize
from tw_ml.datagen.labelrules import load_label_rules
from tw_ml.datagen.matrix import GENERATED_SPLITS, build_plan
from tw_ml.datagen.paths import RepoPaths, default_paths
from tw_ml.datagen.pools import DEFAULT_POOL_SEED, build_pools, load_denylist, write_pools
from tw_ml.datagen.providers import (
    OpenAICompatibleProvider,
    ProviderConfigError,
    load_datagen_config,
    resolve_settings,
)
from tw_ml.datagen.records import DatasetRecord, TriageLabels
from tw_ml.datagen.taxonomy import load_taxonomy
from tw_ml.datagen.validate import check_dataset, read_lines, report_json

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_USAGE: Final = 2
ALL_SPLITS: Final[tuple[str, ...]] = ("train", "val", "test_synth", "test_hard", "test_ood")


def _now() -> datetime:
    return datetime.now(UTC)


def _write(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


def _records(path: Path) -> list[DatasetRecord]:
    return [DatasetRecord.model_validate_json(line) for line in read_lines(path) if line.strip()]


# --------------------------------------------------------------------------- commands


def cmd_plan(args: argparse.Namespace, paths: RepoPaths) -> int:
    """Print (or write) the diagnostics of a split's plan."""
    ctx = gen.load_context(paths, args.split)
    plan = build_plan(ctx.plan_inputs(), args.split)
    report = asdict(plan.report)
    report.update(
        {
            "cells": len(plan.cells),
            "plan_sha256": plan.plan_sha256,
            "matrix_sha256": plan.matrix_sha256,
        }
    )
    if args.json:
        Path(args.json).write_text(_json(report) + "\n", encoding="utf-8")
    _write(
        _json(
            {
                k: report[k]
                for k in (
                    "cells",
                    "quotas",
                    "strata",
                    "strata_shortfalls",
                    "feasible_pairs",
                    "top_up_swaps",
                    "plan_sha256",
                )
            }
        )
    )
    _write(f"coverage gaps: {len(plan.report.coverage_gaps)}")
    return EXIT_FAILED if plan.report.coverage_gaps or plan.report.strata_shortfalls else EXIT_OK


def cmd_pools(args: argparse.Namespace, paths: RepoPaths) -> int:
    """Build or check the split-disjoint pools."""
    pools = build_pools(args.seed, denylist=load_denylist(paths.pools_dir / "brand_denylist.txt"))
    stale = write_pools(paths.pools_dir, pools, args.seed, check=args.check)
    names = [p.relative_to(paths.root).as_posix() for p in stale]
    if args.check and stale:
        sys.stderr.write(
            "pools are stale; run `python -m tw_ml.datagen pools`:\n  " + "\n  ".join(names) + "\n"
        )
        return EXIT_FAILED
    _write("Updated:\n  " + "\n  ".join(names) if stale else "Pools up to date.")
    return EXIT_OK


def cmd_generate(args: argparse.Namespace, paths: RepoPaths) -> int:
    """Generate (or dry-run) the next cells of a split."""
    ctx = gen.load_context(paths, args.split)
    options = gen.RunOptions(
        split=args.split,
        family=args.family,
        n=args.n,
        dry_run=args.dry_run,
        budget_usd=Decimal(str(args.budget_usd)) if args.budget_usd is not None else None,
        out_dir=Path(args.out) if args.out else None,
        terms_reviewed=args.terms_reviewed,
    )
    provider: OpenAICompatibleProvider | None = None
    if not args.dry_run:
        try:
            settings = resolve_settings(
                args.family, ctx.config, os.environ, host=args.host, key_lookup=keys.load_key
            )
        except ProviderConfigError as exc:
            sys.stderr.write(f"provider configuration: {exc}\n")
            return EXIT_USAGE
        provider = OpenAICompatibleProvider(settings)
    try:
        summary = gen.run_generation(ctx, options, provider)
    except gen.GenerationError as exc:
        sys.stderr.write(f"generation refused: {exc}\n")
        return EXIT_USAGE
    finally:
        if provider is not None:
            provider.close()
    _write(_json(asdict(summary)))
    return EXIT_FAILED if summary.stop_reason == "auth" else EXIT_OK


def cmd_validate(args: argparse.Namespace, paths: RepoPaths) -> int:
    """Validate a split file (T-DATA-provenance, rules, duplicates, soft gates)."""
    split = args.split
    source = Path(args.file) if args.file else paths.generated_dir / split / gen.RECORDS_FILE
    ctx = gen.load_context(paths, split) if split in GENERATED_SPLITS else None
    if ctx is None:
        taxonomy = load_taxonomy(paths.schemas_dir)
        rules = load_label_rules(paths.spec_dir / "label_rules.v1.yaml", taxonomy)
        from tw_ml.datagen.factsheet import load_fact_sheet  # noqa: PLC0415 - rarely used path
        from tw_ml.datagen.validate import ValidationContext  # noqa: PLC0415

        vctx = ValidationContext(
            rules, load_fact_sheet(paths.spec_dir / "fact_sheet.v1.md", taxonomy)
        )
        keywords: dict[str, list[str]] = {}
    else:
        vctx = ctx.validation_context
        keywords = {
            i: list(c.banned_words)
            for i, c in ctx.matrix.spec.intents.items()
            if ctx.rules.is_critical(i)
        }
    report = check_dataset(read_lines(source), split, vctx, keywords)
    text = report_json(report)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    _write(text)
    return EXIT_OK if report.passed else EXIT_FAILED


def cmd_leakage(args: argparse.Namespace, paths: RepoPaths) -> int:
    """Run C1-C7 and write the report."""
    cfg = leakage.load_leakage_config(paths.configs_dir / "leakage.yaml")
    inputs = (
        dict(item.split("=", 1) for item in args.input) if args.input else _default_inputs(paths)
    )
    items: list[leakage.LeakItem] = []
    files: dict[str, str] = {}
    for split, file_name in sorted(inputs.items()):
        path = Path(file_name)
        if split == "test_hard" and path.suffix == ".jsonl" and _is_hard_set(path):
            rows = _hard_rows(path, paths)
        else:
            rows = [json.loads(line) for line in read_lines(path) if line.strip()]
        items.extend(leakage.item_from_row(row) for row in rows)
        files[split] = leakage.file_sha256(path)
    embedder, status = leakage.load_embedder(cfg.embedding)
    report = leakage.run_leakage(
        leakage.LeakageInputs(
            items=items,
            protected_strings=leakage.read_protected_strings(
                paths.root / cfg.protected.strings_file
            ),
            kb=leakage.kb_texts(Path(args.kb_dir) if args.kb_dir else paths.kb_dir),
            echo_sources={
                s: leakage.prompt_source_text(paths.root / s) for s in cfg.prompt_echo.sources
            },
        ),
        cfg,
        embedder=embedder,
        embedding_status=status,
        now=_now(),
    )
    report.input_files = files
    out = Path(args.out) if args.out else paths.reports_dir / f"leakage_{_now():%Y-%m-%d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_json(), encoding="utf-8")
    if args.write_filtered:
        _write_filtered(Path(args.write_filtered), inputs, report.drops)
    _write(
        _json(
            {
                "gate": report.gate,
                "counts": report.counts,
                "drops": len(report.drops),
                "report": str(out),
            }
        )
    )
    return EXIT_OK if report.gate["passed"] else EXIT_FAILED


def _default_inputs(paths: RepoPaths) -> dict[str, str]:
    candidates = {
        split: paths.generated_dir / split / gen.RECORDS_FILE
        for split in ("train", "val", "test_synth", "test_ood")
    }
    candidates["test_hard"] = paths.hard_set_file
    return {split: str(path) for split, path in candidates.items() if path.is_file()}


def _is_hard_set(path: Path) -> bool:
    first = next((line for line in read_lines(path) if line.strip()), "{}")
    return "provenance" not in json.loads(first)


def _hard_rows(path: Path, paths: RepoPaths) -> list[dict[str, Any]]:
    taxonomy = load_taxonomy(paths.schemas_dir)
    items = [
        hardset.HardSetItem.model_validate_json(line)
        for line in read_lines(path)
        if line.strip() and hardset.TEMPLATE_ID not in line
    ]
    return [json.loads(hardset.to_record(item, taxonomy).model_dump_json()) for item in items]


def _write_filtered(folder: Path, inputs: dict[str, str], drops: Sequence[str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val"):
        if split in inputs:
            rows = [json.loads(line) for line in read_lines(Path(inputs[split])) if line.strip()]
            kept = leakage.apply_drops(rows, drops)
            text = "".join(
                json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in kept
            )
            (folder / f"{split}.jsonl").write_text(text, encoding="utf-8", newline="\n")


def cmd_qa(args: argparse.Namespace, paths: RepoPaths) -> int:
    """Audit sampling, scoring and inter-annotator agreement."""
    if args.qa_command == "sample":
        records = _records(
            Path(args.file) if args.file else paths.generated_dir / "train" / gen.RECORDS_FILE
        )
        sample = qa.audit_sample(records, args.n, args.seed)
        folder = Path(args.out_dir)
        folder.mkdir(parents=True, exist_ok=True)
        sheet = qa.blind_sheet(sample, args.seed)
        (folder / "audit_blind.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sheet), encoding="utf-8"
        )
        dumped = {r.record_id: r.labels.model_dump(mode="json") for r in sample}
        (folder / "audit_proposals.json").write_text(_json(dumped) + "\n", encoding="utf-8")
        _write(f"audit sample: {len(sample)} records (seed {args.seed}) -> {folder}")
        return EXIT_OK
    if args.qa_command == "score":
        raw = json.loads(Path(args.proposals).read_text(encoding="utf-8"))
        proposals = {rid: TriageLabels.model_validate(v) for rid, v in raw.items()}
        reviews = [
            qa.AuditReview.model_validate_json(line)
            for line in read_lines(Path(args.reviews))
            if line.strip()
        ]
        result = qa.score_audit(proposals, reviews)
        _write(_json(asdict(result)))
        return EXIT_OK if result.passed else EXIT_FAILED
    first = [json.loads(line)[args.field] for line in read_lines(Path(args.a)) if line.strip()]
    second = [json.loads(line)[args.field] for line in read_lines(Path(args.b)) if line.strip()]
    summary = qa.agreement(
        [str(v) for v in first], [str(v) for v in second], n_resamples=args.n_resamples
    )
    _write(_json(asdict(summary)))
    return EXIT_OK if summary.meets_threshold else EXIT_FAILED


def cmd_manifest(args: argparse.Namespace, paths: RepoPaths) -> int:
    """Build, freeze or verify split manifests."""
    if args.manifest_command == "verify":
        splits = (
            [args.split]
            if args.split
            else [p.stem for p in sorted(paths.manifests_dir.glob("*.json")) if "." not in p.stem]
        )
        failures = 0
        for split in splits:
            problems = manifest.verify_manifest(
                manifest.load_manifest(manifest.manifest_path(paths.manifests_dir, split)),
                paths.root,
            )
            failures += bool(problems)
            _write(f"{split}: {'OK' if not problems else '; '.join(problems)}")
        return EXIT_FAILED if failures else EXIT_OK
    files = [Path(f) for f in args.file]
    subsets: dict[str, list[str]] = {}
    seeds: dict[str, int] = {}
    if args.val_dev:
        rows = [json.loads(line) for f in files for line in read_lines(f) if line.strip()]
        subsets["val_dev"] = manifest.val_dev_subset(rows)
        seeds["val_dev"] = manifest.VAL_DEV_SEED
    built = manifest.build_manifest(
        args.split,
        files,
        paths.root,
        now=_now(),
        version=args.version,
        subsets=subsets,
        subset_seeds=seeds,
    )
    target = manifest.manifest_path(paths.manifests_dir, args.split)
    if args.manifest_command == "freeze":
        try:
            built = manifest.freeze(target, built, now=_now(), bump=args.bump)
        except manifest.ManifestError as exc:
            sys.stderr.write(f"{exc}\n")
            return EXIT_FAILED
    else:
        manifest.write_manifest(target, built)
    where = target.relative_to(paths.root).as_posix()
    _write(f"{where}: {built.records} records, {built.dataset_version}, frozen={built.frozen}")
    return EXIT_OK


def cmd_hardset(args: argparse.Namespace, paths: RepoPaths) -> int:
    """Validate or split the hard set."""
    taxonomy = load_taxonomy(paths.schemas_dir)
    ctx = gen.load_context(paths, "train").validation_context
    source = Path(args.file) if args.file else paths.hard_set_file
    report = hardset.validate_hard_set(read_lines(source), ctx, taxonomy)
    if args.hardset_command == "validate" or not report.passed:
        _write(
            _json(
                {
                    "passed": report.passed,
                    "items": len(report.items),
                    "parse_errors": report.parse_errors,
                    "findings": {k: [f.as_dict() for f in v] for k, v in report.findings.items()},
                    "duplicate_ids": report.duplicate_ids,
                    "duplicate_texts": report.duplicate_texts,
                    "quota_shortfalls": report.quota_shortfalls,
                    "counts": report.counts,
                }
            )
        )
        return EXIT_OK if report.passed else EXIT_FAILED
    dev, final = hardset.split_hard_set(report.items, seed=args.seed)
    rules = load_label_rules(paths.spec_dir / "label_rules.v1.yaml", taxonomy)
    _write(
        _json(
            {
                "hard_dev": dev,
                "hard_final_count": len(final),
                "strata": hardset.split_summary(report.items, dev, rules),
            }
        )
    )
    if args.write_manifest:
        built = manifest.build_manifest(
            "test_hard",
            [source],
            paths.root,
            now=_now(),
            subsets={"hard_dev": dev, "hard_final": final},
            subset_seeds={"hard_dev": args.seed, "hard_final": args.seed},
        )
        manifest.write_manifest(manifest.manifest_path(paths.manifests_dir, "test_hard"), built)
        gold = paths.hard_dev_gold_file
        gold.parent.mkdir(parents=True, exist_ok=True)
        lines = hardset.dev_gold_lines(report.items, dev)
        gold.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n")
    return EXIT_OK


def cmd_bitext(args: argparse.Namespace, paths: RepoPaths) -> int:
    """Build or materialize the Bitext OOD set (downloads only with --allow-download)."""
    if not args.allow_download:
        sys.stderr.write(
            "refusing to download Bitext data without --allow-download (owner-run only)\n"
        )
        return EXIT_USAGE
    taxonomy = load_taxonomy(paths.schemas_dir)
    mapping = load_mapping(paths.spec_dir / "bitext_mapping.v1.yaml", taxonomy)
    source = HFRowSource()
    pointers_path = (
        Path(args.pointers) if args.pointers else paths.ood_dir / "test_ood.v1.pointers.jsonl"
    )
    records_path = (
        Path(args.records_out)
        if args.records_out
        else paths.generated_dir / "test_ood" / gen.RECORDS_FILE
    )
    if args.bitext_command == "build":
        rejects = (
            {
                (str(r["source"]), int(r["row"]))
                for r in gen.read_jsonl(Path(args.rejects))
                if r.get("decision") == "reject"
            }
            if args.rejects
            else set()
        )
        build = build_ood(mapping, source, taxonomy, now=_now(), rejects=rejects)
        pointers_path.parent.mkdir(parents=True, exist_ok=True)
        pointers_path.write_text(
            "".join(json.dumps(p, sort_keys=True) + "\n" for p in build.pointers),
            encoding="utf-8",
            newline="\n",
        )
        records = build.records
        _write(
            _json(
                {
                    "pointers": str(pointers_path),
                    "records": len(records),
                    "skipped": build.skipped,
                    "pii_flags": build.pii_flags,
                }
            )
        )
    else:
        pointers = list(gen.read_jsonl(pointers_path))
        records = materialize(pointers, mapping, source, taxonomy, now=_now())
    records_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.write_text(
        "".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8", newline="\n"
    )
    _write(f"materialized {len(records)} records (gitignored) -> {records_path}")
    return EXIT_OK


def cmd_keys(args: argparse.Namespace, paths: RepoPaths) -> int:
    """Store, inspect or delete generator API keys in the OS credential store."""
    config = load_datagen_config(paths.configs_dir / "datagen.yaml")
    if args.keys_command == "status":
        _write("credential store: " + ", ".join(keys.backend_names()))
        for family, family_config in sorted(config.families.items()):
            env_name = f"TW_DATAGEN_{family}_API_KEY"
            override = (
                " (overridden by the environment variable)" if os.environ.get(env_name) else ""
            )
            for host in sorted(family_config.hosts):
                stored = keys.key_status(family, host)
                _write(f"  {keys.credential_name(family, host):<16} {stored}{override}")
        return EXIT_OK
    host = args.host or config.families[args.family].default_host
    if host not in config.families[args.family].hosts:
        sys.stderr.write(f"unknown host {host!r} for family {args.family}\n")
        return EXIT_USAGE
    name = keys.credential_name(args.family, host)
    try:
        if args.keys_command == "delete":
            removed = keys.delete_key(args.family, host)
            _write(f"removed {name}" if removed else f"nothing stored for {name}")
            return EXIT_OK
        secret = getpass.getpass(f"API key for {name} (input hidden, press Enter when done): ")
        keys.store_key(args.family, host, secret)
    except keys.KeyStoreError as exc:
        sys.stderr.write(f"key store: {exc}\n")
        return EXIT_USAGE
    _write(f"stored {name} in {keys.backend_names()[0]}; the key itself is never printed")
    return EXIT_OK


# --------------------------------------------------------------------------- parser


Subparsers = Any  # argparse's _SubParsersAction is private; the helpers only call add_parser


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m tw_ml.datagen", description=__doc__.splitlines()[0] if __doc__ else None
    )
    sub = parser.add_subparsers(dest="command", required=True)
    _add_plan_pools(sub)
    _add_generate(sub)
    _add_validate_leakage(sub)
    _add_qa(sub)
    _add_manifest(sub)
    _add_hardset_bitext(sub)
    _add_keys(sub)
    return parser


def _add_plan_pools(sub: Subparsers) -> None:
    plan = sub.add_parser("plan", help="plan diagnostics for a split")
    plan.add_argument("--split", required=True, choices=GENERATED_SPLITS)
    plan.add_argument("--json", help="write the full report to this file")
    pools = sub.add_parser("pools", help="build or check data/spec/pools")
    pools.add_argument("--check", action="store_true")
    pools.add_argument("--seed", type=int, default=DEFAULT_POOL_SEED)


def _add_generate(sub: Subparsers) -> None:
    generate = sub.add_parser("generate", help="generate records (resumable, budget-capped)")
    generate.add_argument("--split", required=True, choices=GENERATED_SPLITS)
    generate.add_argument("--family", required=True, choices=("A", "B"))
    generate.add_argument("--n", type=int, required=True)
    generate.add_argument("--dry-run", action="store_true", help="render prompts only; no network")
    generate.add_argument("--budget-usd", type=float, help="cap for this run (default: remaining)")
    generate.add_argument("--host", help="host profile from ml/configs/datagen.yaml (e.g. groq)")
    generate.add_argument("--out", help="output directory (default data/generated/<split>)")
    generate.add_argument("--terms-reviewed", action="store_true", help="vendor terms re-reviewed")


def _add_validate_leakage(sub: Subparsers) -> None:
    validate = sub.add_parser("validate", help="validate a split file")
    validate.add_argument("--split", required=True, choices=ALL_SPLITS)
    validate.add_argument("--file")
    validate.add_argument("--report")
    leak = sub.add_parser("leakage", help="leakage checks C1-C7")
    leak.add_argument("--input", action="append", help="SPLIT=FILE (repeatable)")
    leak.add_argument("--kb-dir")
    leak.add_argument("--out")
    leak.add_argument("--write-filtered", help="write train/val without dropped records here")


def _add_qa(sub: Subparsers) -> None:
    qa_parser = sub.add_parser("qa", help="label QA")
    qa_sub = qa_parser.add_subparsers(dest="qa_command", required=True)
    sample = qa_sub.add_parser("sample")
    sample.add_argument("--file")
    sample.add_argument("--n", type=int, default=qa.AUDIT_SIZE)
    sample.add_argument("--seed", type=int, default=qa.AUDIT_SEED)
    sample.add_argument("--out-dir", required=True)
    score = qa_sub.add_parser("score")
    score.add_argument("--proposals", required=True)
    score.add_argument("--reviews", required=True)
    kappa = qa_sub.add_parser("kappa")
    kappa.add_argument("--a", required=True)
    kappa.add_argument("--b", required=True)
    kappa.add_argument("--field", default="intent")
    kappa.add_argument("--n-resamples", type=int, default=10_000)


def _add_manifest(sub: Subparsers) -> None:
    man = sub.add_parser("manifest", help="content-hash manifests")
    man_sub = man.add_subparsers(dest="manifest_command", required=True)
    for name in ("build", "freeze"):
        cmd = man_sub.add_parser(name)
        cmd.add_argument("--split", required=True, choices=ALL_SPLITS)
        cmd.add_argument("--file", action="append", required=True)
        cmd.add_argument("--version", default="v1")
        cmd.add_argument("--val-dev", action="store_true", help="record the val_dev subset")
        if name == "freeze":
            cmd.add_argument("--bump", action="store_true", help="version a changed frozen split")
    verify = man_sub.add_parser("verify")
    verify.add_argument("--split", choices=ALL_SPLITS)


def _add_hardset_bitext(sub: Subparsers) -> None:
    hard = sub.add_parser("hardset", help="hard-set validation and split")
    hard_sub = hard.add_subparsers(dest="hardset_command", required=True)
    hard_validate = hard_sub.add_parser("validate")
    hard_validate.add_argument("--file")
    hard_split = hard_sub.add_parser("split")
    hard_split.add_argument("--file")
    hard_split.add_argument("--seed", type=int, default=hardset.HARD_SPLIT_SEED)
    hard_split.add_argument(
        "--write-manifest",
        action="store_true",
        help="freeze the split: data/manifests/test_hard.json + the open evals/hard_dev.v1.jsonl",
    )
    bitext = sub.add_parser("bitext", help="Bitext OOD pointers (downloads; owner-run only)")
    bitext_sub = bitext.add_subparsers(dest="bitext_command", required=True)
    for name in ("build", "materialize"):
        cmd = bitext_sub.add_parser(name)
        cmd.add_argument("--allow-download", action="store_true")
        cmd.add_argument("--pointers")
        cmd.add_argument("--records-out")
        if name == "build":
            cmd.add_argument("--rejects", help="evals/ood/review_decisions.v1.jsonl")


def _add_keys(sub: Subparsers) -> None:
    keys_parser = sub.add_parser("keys", help="generator API keys in the OS credential store")
    keys_sub = keys_parser.add_subparsers(dest="keys_command", required=True)
    keys_sub.add_parser("status", help="show which keys are stored (never the values)")
    for name, help_text in (("set", "store a key (hidden prompt)"), ("delete", "remove a key")):
        cmd = keys_sub.add_parser(name, help=help_text)
        cmd.add_argument("--family", required=True, choices=("A", "B"))
        cmd.add_argument("--host", help="host profile (default: the family's default host)")


COMMANDS: Final = {
    "plan": cmd_plan,
    "pools": cmd_pools,
    "generate": cmd_generate,
    "validate": cmd_validate,
    "leakage": cmd_leakage,
    "qa": cmd_qa,
    "manifest": cmd_manifest,
    "hardset": cmd_hardset,
    "bitext": cmd_bitext,
    "keys": cmd_keys,
}


def main(argv: Sequence[str] | None = None, paths: RepoPaths | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Arguments (defaults to ``sys.argv[1:]``).
        paths: Repository paths override (tests).

    Returns:
        Process exit code.
    """
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args, paths or default_paths())


if __name__ == "__main__":
    raise SystemExit(main())
