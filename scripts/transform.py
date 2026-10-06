"""
transform.py
------------
Transform the raw PokeAPI JSON (data/raw/*.json) into a clean tabular dataset
(data/processed/clean.json).

The file is the second step of the ETL pipeline (extract -> transform -> load).
It can be run standalone from the command line, or imported and called by
Airflow through ``transform_data()``.

Input
-----
    data/raw/YYYY-MM-DD.json  (today's UTC date by default)
        Expected structure::

            {
              "pokemons": [ { ...raw PokeAPI payload... }, ... ]
            }

Output
------
    data/processed/clean.json
        A list of flat records (orient="records"), one record per Pokémon,
        with the following columns:

        id, name, height_m, weight_kg, base_experience,
        type_primary, type_secondary,
        hp, attack, defense, special_attack, special_defense, speed,
        stat_total, power_tier,
        ability_primary, is_hidden_ability, sprite_url

Transformations applied
-----------------------
  1. Flatten the nested JSON into rows (1 row = 1 Pokémon)
  2. Drop duplicates on the ID
  3. Cast/normalize data types (int, float, bool, string)
  4. Rename and normalize columns
  5. Create computed columns: stat_total, power_tier
  6. Filter out invalid records
  7. Sort by id for a stable dataset

Configuration
-------------
    RAW_DIR        input folder      (env var ``RAW_DIR``,       default ``data/raw``)
    PROCESSED_DIR  output folder     (env var ``PROCESSED_DIR``, default ``data/processed``)

Usage
-----
    CLI::

        python scripts/transform.py

    As a function::

        from scripts.transform import transform_data
        path = transform_data()            # -> "data/processed/clean.json"
        path = transform_data("data/raw/2026-10-06.json")
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = Path(os.getenv("RAW_DIR", PROJECT_ROOT / "data" / "raw"))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", PROJECT_ROOT / "data" / "processed"))

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def _get_stat(stats: list[dict], stat_name: str) -> int | None:
    """Return the value of a given stat from the PokeAPI ``stats`` list."""
    for s in stats:
        if s.get("stat", {}).get("name") == stat_name:
            return s.get("base_stat")
    return None


def _get_type(types: list[dict], slot: int) -> str | None:
    """Return the type at the given slot (1 = primary, 2 = secondary)."""
    for t in types:
        if t.get("slot") == slot:
            return t.get("type", {}).get("name")
    return None


def _power_tier(total: int) -> str:
    """Categorize a Pokémon based on the sum of its base stats."""
    if total >= 600:
        return "elite"      # legendary and pseudo-legendary
    if total >= 500:
        return "high"
    if total >= 400:
        return "mid"
    return "low"


def flatten_pokemon(p: dict) -> dict:
    """Turn one raw (nested) Pokémon into a single flat row."""
    stats = p.get("stats", [])
    types = p.get("types", [])
    abilities = p.get("abilities", [])

    stat_values = {
        "hp":              _get_stat(stats, "hp"),
        "attack":          _get_stat(stats, "attack"),
        "defense":         _get_stat(stats, "defense"),
        "special_attack":  _get_stat(stats, "special-attack"),
        "special_defense": _get_stat(stats, "special-defense"),
        "speed":           _get_stat(stats, "speed"),
    }

    stat_total = sum(v for v in stat_values.values() if v is not None)

    primary_ability = abilities[0] if abilities else {}

    return {
        "id":                 p.get("id"),
        "name":               (p.get("name") or "").capitalize(),
        "height_m":           (p.get("height") or 0) / 10,
        "weight_kg":          (p.get("weight") or 0) / 10,
        "base_experience":    p.get("base_experience"),
        "type_primary":       _get_type(types, 1),
        "type_secondary":     _get_type(types, 2),   # None if there is no 2nd type
        **stat_values,
        "stat_total":         stat_total,
        "power_tier":         _power_tier(stat_total),
        "ability_primary":    primary_ability.get("ability", {}).get("name"),
        "is_hidden_ability":  bool(primary_ability.get("is_hidden", False)),
        "sprite_url":         (p.get("sprites") or {}).get("front_default"),
    }
    stats = p.get("stats", [])
    types = p.get("types", [])
    abilities = p.get("abilities", [])

    stat_values = {
        "hp":              _get_stat(stats, "hp"),
        "attack":          _get_stat(stats, "attack"),
        "defense":         _get_stat(stats, "defense"),
        "special_attack":  _get_stat(stats, "special-attack"),
        "special_defense": _get_stat(stats, "special-defense"),
        "speed":           _get_stat(stats, "speed"),
    }

    stat_total = sum(v for v in stat_values.values() if v is not None)

    primary_ability = abilities[0] if abilities else {}

    return {
        "id":                 p.get("id"),
        "name":               (p.get("name") or "").capitalize(),
        "height_m":           (p.get("height") or 0) / 10,
        "weight_kg":          (p.get("weight") or 0) / 10,
        "base_experience":    p.get("base_experience"),
        "type_primary":       _get_type(types, 1),
        "type_secondary":     _get_type(types, 2),   # None si pas de 2e type
        **stat_values,
        "stat_total":         stat_total,
        "power_tier":         _power_tier(stat_total),
        "ability_primary":    primary_ability.get("ability", {}).get("name"),
        "is_hidden_ability":  bool(primary_ability.get("is_hidden", False)),
        "sprite_url":         (p.get("sprites") or {}).get("front_default"),
    }


def transform_data(input_file: str | None = None) -> str:
    """
    Main function called by Airflow.
    Reads the raw JSON of the day, transforms it, and writes the clean file.

    Args:
        input_file: path to the raw JSON file. Defaults to
            ``data/raw/<today's UTC date>.json``.

    Returns:
        The path of the transformed (clean) file.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Pick the input file
    if input_file is None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        input_file = RAW_DIR / f"{today}.json"
    input_file = Path(input_file)

    if not input_file.exists():
        raise FileNotFoundError(f"Raw file not found: {input_file}")

    logger.info(f"Reading raw file: {input_file}")

    # 2. Load
    with open(input_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    pokemons = raw.get("pokemons", [])
    logger.info(f"{len(pokemons)} Pokémon read from the raw file")

    if not pokemons:
        raise ValueError("No Pokémon in the raw file")

    # 3. Flatten
    rows = [flatten_pokemon(p) for p in pokemons]
    df = pd.DataFrame(rows)
    logger.info(f"After flattening: {len(df)} rows")

    # 4. Drop duplicates
    before = len(df)
    df = df.drop_duplicates(subset=["id"], keep="first")
    logger.info(f"Duplicates dropped: {before - len(df)}")

    # 5. Filtering: keep only valid rows
    before = len(df)
    df = df[
        df["id"].notna()
        & df["name"].notna()
        & (df["name"].str.len() > 0)
        & df["type_primary"].notna()
    ]
    logger.info(f"Invalid rows filtered out: {before - len(df)}")

    # 6. Type casting (nullable to handle None values)
    df["id"] = df["id"].astype("Int64")
    df["base_experience"] = df["base_experience"].astype("Int64")
    for col in ["hp", "attack", "defense", "special_attack",
                "special_defense", "speed", "stat_total"]:
        df[col] = df[col].astype("Int64")
    df["height_m"] = df["height_m"].astype("float64")
    df["weight_kg"] = df["weight_kg"].astype("float64")
    df["is_hidden_ability"] = df["is_hidden_ability"].astype("bool")
    df["type_primary"] = df["type_primary"].astype("string")
    df["type_secondary"] = df["type_secondary"].astype("string")
    df["power_tier"] = df["power_tier"].astype("string")

    # 7. Sort by id for a stable dataset
    df = df.sort_values("id").reset_index(drop=True)

    # 8. Write
    output_file = PROCESSED_DIR / "clean.json"
    df.to_json(output_file, orient="records", indent=2, force_ascii=False)

    logger.info(f"Transformed file written: {output_file}")
    logger.info(f"Summary: {len(df)} Pokémon, {len(df.columns)} columns")

    return str(output_file)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    path = transform_data()
    print(f"\nTransformation done: {path}")

    # Quick preview
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"\nPreview ({len(data)} Pokémon):")
    for p in data[:3]:
        print(f"  #{p['id']:>3} {p['name']:<12} "
              f"types={p['type_primary']}/{p['type_secondary'] or '-'} "
              f"total={p['stat_total']} tier={p['power_tier']}")