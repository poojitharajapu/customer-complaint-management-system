"""Integrated reproducible pipeline from source entities through Phase 7 outcomes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from generator.anomalies import AnomalyRecord, generate_anomalies
from generator.config import RANDOM_SEED
from generator.ground_truth import GroundTruthLabel, build_ground_truth
from generator.phase7 import Phase7Dataset, generate_phase7_dataset
from generator.validation import ValidationReport, validate_complete_dataset


@dataclass
class CompleteDataset:
    phase7: Phase7Dataset
    ground_truth: list[GroundTruthLabel]
    anomalies: list[AnomalyRecord]
    validation: ValidationReport
    mode: str
    seed: int


def generate_complete_dataset(mode: str = "starter", seed: int = RANDOM_SEED) -> CompleteDataset:
    """Generate all supported entities in dependency order and validate the valid baseline."""
    normalized = mode.strip().lower()
    if normalized not in {"starter", "full"}:
        raise ValueError("mode must be 'starter' or 'full'")
    phase7 = generate_phase7_dataset(normalized, seed)
    labels = build_ground_truth(phase7.phase6.complaints, phase7.phase6.sla_clocks)
    anomalies = generate_anomalies()
    result = CompleteDataset(phase7, labels, anomalies, None, normalized, seed)  # type: ignore[arg-type]
    result.validation = validate_complete_dataset(result)
    return result


def main() -> int:
    """Generate and report an in-memory complete dataset; optionally export it."""
    parser = argparse.ArgumentParser(description="Generate and validate the Phase 8 dataset.")
    parser.add_argument("--mode", choices=("starter", "full"), default="starter")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--export", action="store_true", help="Write deterministic exports to the configured output directory.")
    parser.add_argument("--output", default=None, help="Override export directory.")
    args = parser.parse_args()
    dataset = generate_complete_dataset(args.mode, args.seed)
    print(f"Phase 8 {args.mode.title()} dataset (seed={args.seed})")
    for name, count in dataset.validation.entity_counts.items(): print(f"  {name}: {count}")
    print(f"Validation: {dataset.validation.passed_checks}/{dataset.validation.total_checks} passed; {dataset.validation.failed_checks} failed.")
    print("Metrics (rate = current resolved/closed complaints / all complaints):")
    for name, value in dataset.phase7.metrics.items(): print(f"  {name}: {value}")
    for warning in dataset.validation.warnings: print(f"Warning: {warning}")
    if args.export:
        from generator.export import export_complete_dataset
        paths = export_complete_dataset(dataset, args.output)
        print(f"Exported {len(paths)} files to {args.output or 'data/generated'}")
    if dataset.validation.failed_checks:
        for error in dataset.validation.errors: print(f"FAILED {error['check']}: {error['detail']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
