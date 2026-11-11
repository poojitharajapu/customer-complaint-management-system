"""Build the complete Phase 7 dataset on top of Phase 6, in memory only."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from backend.models.resolution import Resolution
from backend.models.survey import Survey
from generator.config import RANDOM_SEED
from generator.metrics import calculate_resolution_feedback_metrics
from generator.phase6 import Phase6Dataset, generate_phase6_dataset
from generator.resolutions import generate_resolutions
from generator.surveys import generate_surveys


@dataclass
class Phase7Dataset:
    """Keep the Phase 6 graph and Phase 7 outcomes together for later validation/export."""

    phase6: Phase6Dataset
    resolutions: list[Resolution]
    surveys: list[Survey]
    metrics: dict[str, int | object]


def generate_phase7_dataset(mode: str = "starter", seed: int = RANDOM_SEED) -> Phase7Dataset:
    """Generate Phase 6 records, then resolutions, closure/reopen history, surveys, and metrics."""
    phase6 = generate_phase6_dataset(mode=mode, seed=seed)
    resolutions = generate_resolutions(phase6.complaints, phase6.agents, seed=seed)
    surveys = generate_surveys(phase6.complaints, seed=seed)
    metrics = calculate_resolution_feedback_metrics(phase6.complaints, resolutions, surveys)
    return Phase7Dataset(phase6=phase6, resolutions=resolutions, surveys=surveys, metrics=metrics)


def main() -> int:
    """Run Phase 7 in memory and print generated record counts and calculated metrics."""
    parser = argparse.ArgumentParser(description="Generate and summarize the Phase 7 dataset in memory.")
    parser.add_argument("--mode", choices=("starter", "full"), default="starter")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()
    dataset = generate_phase7_dataset(mode=args.mode, seed=args.seed)
    phase6 = dataset.phase6
    print(f"Generated Phase 7 {args.mode.title()} dataset (seed={args.seed}):")
    print(f"  complaints: {len(phase6.complaints)}")
    print(f"  resolutions: {len(dataset.resolutions)}")
    print(f"  status history: {sum(len(complaint.status_history) for complaint in phase6.complaints)}")
    print(f"  reopen history: {sum(len(complaint.reopen_history) for complaint in phase6.complaints)}")
    print(f"  surveys: {len(dataset.surveys)}")
    print("Metrics:")
    for name, value in dataset.metrics.items():
        print(f"  {name}: {value}")
    print("Records remain in memory; no database writes were performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
