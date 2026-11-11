"""
Application Configuration Settings.

This module centralizes configuration values such as project metadata,
server host/port, and SQLite database file path.
"""

from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Application metadata
APP_TITLE = "Customer Complaint Management and SLA Tracking System"
APP_DESCRIPTION = "API for managing customer complaints and tracking Service Level Agreements (SLAs)"
APP_VERSION = "1.0.0"

# Server configuration
HOST = "127.0.0.1"
PORT = 8000

# Database configuration (SQLite)
DATA_DIR = BASE_DIR / "data"
DATABASE_URL = f"sqlite:///{DATA_DIR / 'complaints.db'}"

