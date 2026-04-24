"""
Configuration for ClawSeries real backend.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# Data subdirectories
SCRIPTS_DIR = DATA_DIR / "scripts"
ASSETS_DIR = DATA_DIR / "assets"
RENDERS_DIR = DATA_DIR / "renders"
OUTPUTS_DIR = DATA_DIR / "outputs"
CHROMA_DIR = DATA_DIR / "chroma"
DUBBING_DIR = DATA_DIR / "dubbing"

# Database
DB_PATH = DATA_DIR / "clawseries.db"

# Ensure directories exist
for d in [DATA_DIR, SCRIPTS_DIR, ASSETS_DIR, RENDERS_DIR, OUTPUTS_DIR, CHROMA_DIR, DUBBING_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def get_db_url() -> str:
    return f"sqlite:///{DB_PATH}"
