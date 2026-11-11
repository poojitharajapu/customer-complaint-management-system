"""Shared settings for the synthetic customer complaint data generator.

This module only defines configuration. Importing it does not create files,
connect to the application database, or generate any records.
"""

from pathlib import Path

# Resolve paths from this file so the generator works from any current directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENERATOR_OUTPUT_DIR = PROJECT_ROOT / "data" / "generated"

# Keep the seed and simulated year fixed so repeated runs are reproducible.
RANDOM_SEED = 20261022
DATA_YEAR = 2026

# Dataset sizes for the two supported runs. Both modes will share generation logic.
STARTER_MODE = {
    "customers": 50,
    "orders": 80,
    "complaints": 20,
    "messages": 60,
}

FULL_MODE = {
    "customers": 5_000,
    "orders": 8_000,
    "complaints": 2_000,
    "messages": 6_000,
}

# Values below match the existing SQLAlchemy model constraints.
PRIORITIES = ["Critical", "High", "Medium", "Low"]
COMPLAINT_CATEGORIES = (
    "Billing",
    "Product Quality",
    "Delivery",
    "Technical Support",
    "Account Access",
    "Returns and Refunds",
    "Warranty",
    "Website and App",
    "Customer Service",
    "Safety",
)

# Safety complaints receive the highest supported priority.
SAFETY_CATEGORY = "Safety"
SAFETY_PRIORITY = "Critical"
