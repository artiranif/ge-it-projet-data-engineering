"""
validate.py
------------
Quality control for the transformed dataset (data/processed/clean.json).

The file is the third step of the ETL pipeline (extract -> transform -> validate
-> load). It can be run standalone from the command line, or imported and
called by Airflow through ``validate_data()``.

If any rule is violated it raises a ``ValueError`` -> Airflow marks the task as
**failed** and triggers a retry. The file itself is never modified: validation
is read-only and the path is returned unchanged so it can be chained via XCom.

Input
-----
    data/processed/clean.json  (produced by ``scripts/transform.py``)
        A list of flat records, one per Pokémon, containing at least:

        id, name, type_primary, stat_total, power_tier,
        hp, attack, defense, special_attack, special_defense, speed

Output
------
    The input path, unchanged (returned as a string).

Checks performed
----------------
  1. The file exists
  2. The dataset is non-empty
  3. At least 100 rows (Gen 1 = 151; a threshold of 100 is tolerated)
  4. ``id`` has no missing value
  5. ``id`` is unique (no duplicates)
  6. Required fields are present and non-null:
     ``name``, ``type_primary``, ``stat_total``, ``power_tier``
  7. Every base stat is within a plausible range ``[1, 255]``
  8. ``stat_total`` equals the sum of the six base stats
  9. Every ``power_tier`` is one of ``low`` / ``mid`` / ``high`` / ``elite``

Configuration
-------------
    PROCESSED_DIR  input folder (env var ``PROCESSED_DIR``, default ``data/processed``)

Usage
-----
    CLI::

        python scripts/validate.py

    As a function::

        from scripts.validate import validate_data
        path = validate_data()                       # -> "data/processed/clean.json"
        path = validate_data("data/processed/clean.json")
"""

import json
import logging
import os
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", PROJECT_ROOT / "data" / "processed"))

VALID_TIERS = {"low", "mid", "high", "elite"}


def _check(condition: bool, message: str):
    """Small helper: raise ValueError if the condition is false."""
    if not condition:
        raise ValueError(f"Quality check failed: {message}")
    logger.info(f"OK: {message}")


def validate_data(input_file: str | None = None) -> str:
    """
    Main function called by Airflow.

    Args:
        input_file: path to the clean JSON file. Defaults to
            ``data/processed/clean.json``.

    Returns:
        The path of the validated file (unchanged), so it can be chained via XCom.
    """
    if input_file is None:
        input_file = PROCESSED_DIR / "clean.json"
    input_file = Path(input_file)

    # 1. File exists
    _check(input_file.exists(), f"File found: {input_file}")

    # 2. Load
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    logger.info(f"Dataset loaded: {len(df)} rows, {len(df.columns)} columns")

    # 3. Not empty
    _check(len(df) > 0, f"Dataset is not empty ({len(df)} rows)")

    # 4. Expected count (Gen 1 = 151, at least 100 is tolerated)
    _check(len(df) >= 100, f"At least 100 Pokémon (got {len(df)})")

    # 5. id not null
    _check(df["id"].notna().all(), "No missing id")

    # 6. id unique
    dup = df["id"].duplicated().sum()
    _check(dup == 0, f"No duplicated id (got {dup} duplicates)")

    # 7. Required fields not null
    for col in ["name", "type_primary", "stat_total", "power_tier"]:
        missing = df[col].isna().sum()
        _check(missing == 0, f"'{col}' has no missing value (got {missing})")

    # 8. Stats within a plausible range (1-255)
    stat_cols = ["hp", "attack", "defense", "special_attack",
                 "special_defense", "speed"]
    for col in stat_cols:
        ok = df[col].between(1, 255).all()
        _check(ok, f"'{col}' within [1, 255]")

    # 9. stat_total == sum of the 6 stats
    computed = df[stat_cols].sum(axis=1)
    mismatches = (computed != df["stat_total"]).sum()
    _check(mismatches == 0, f"stat_total is consistent (got {mismatches} mismatches)")

    # 10. Valid power_tier
    invalid_tiers = set(df["power_tier"].unique()) - VALID_TIERS
    _check(not invalid_tiers,
           f"power_tier within {VALID_TIERS} (invalid values: {invalid_tiers})")

    logger.info(f"Validation passed: {len(df)} Pokémon checked")
    return str(input_file)


if __name__ == "__main__":
    path = validate_data()
    print(f"\nValidation OK: {path}")