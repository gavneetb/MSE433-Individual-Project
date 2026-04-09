from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
CACHE_DIR = BACKEND_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

ONTARIO_EV_DATASET_PAGE = (
    "https://data.ontario.ca/en/dataset/"
    "electric-vehicles-in-ontario-by-forward-sortation-area"
)
NREL_STATIONS_URL = "https://developer.nrel.gov/api/alt-fuel-stations/v1.json"
NREL_API_KEY = os.getenv("NREL_API_KEY", "DEMO_KEY")
OVERPASS_API_URL = "https://overpass.kumi.systems/api/interpreter"

ONTARIO_PREFIXES = {"K", "L", "M", "N", "P"}
DEFAULT_FORECAST_HORIZON = 4
DEFAULT_SERVICE_RADIUS_KM = 15.0
DEFAULT_SITE_COUNT = 25
DEFAULT_OBJECTIVE = "coverage"
DEFAULT_CONSTRAINT_MODE = "site_count"

# Scenario-based site costs. These are intentionally simple and user-adjustable.
SITE_TYPE_COSTS = {
    "level2": 120_000,
    "dc_fast": 400_000,
}
