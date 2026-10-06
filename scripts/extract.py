"""
extract.py
----------
Extract Pokémon data from the public PokeAPI.

The file is the first step of the ETL pipeline (extract -> transform -> validate
-> load). It can be run standalone from the command line, or imported and
called by Airflow through ``extract_data()``.

- Fetches the list of the first 151 Pokémon (Gen 1).
- For each Pokémon, fetches its details (types, stats, abilities...).
- Saves the raw JSON to data/raw/YYYY-MM-DD.json (today's date in UTC).
- Returns the file path (usable as an Airflow XCom).

Output
------
    data/raw/YYYY-MM-DD.json
        Raw PokeAPI payloads, shaped as::

            {
              "extracted_at": "<UTC ISO timestamp>",
              "source": "https://pokeapi.co/api/v2",
              "count": <number of Pokémon successfully fetched>,
              "errors": [ "<name of each Pokémon that failed>", ... ],
              "pokemons": [ { ...raw PokeAPI payload... }, ... ]
            }

Configuration
-------------
    DATA_DIR  output folder (env var ``DATA_DIR``, default ``data/raw``)

Constants
---------
    API_BASE                PokeAPI base URL
    POKEMON_LIMIT           number of Pokémon to fetch (Gen 1 = 151)
    REQUEST_TIMEOUT         per-request timeout, in seconds
    SLEEP_BETWEEN_REQUESTS  pause between requests, to stay polite with the API

Guard rail
----------
    Raises ``RuntimeError`` if fewer than 50 % of the Pokémon were fetched.

Usage
-----
    CLI::

        python scripts/extract.py

    As a function::

        from scripts.extract import extract_data
        path = extract_data()      # -> "data/raw/YYYY-MM-DD.json"
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

API_BASE = "https://pokeapi.co/api/v2"

# Number of Pokémon to fetch (Gen 1 = 151)
POKEMON_LIMIT = 151

# Project root = parent folder of scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data" / "raw"))

REQUEST_TIMEOUT = 15
# PokeAPI has no official rate limit, but we stay fair-play
SLEEP_BETWEEN_REQUESTS = 0.1


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def fetch_pokemon_list(limit: int = POKEMON_LIMIT) -> list[dict]:
    """
    Fetch the list of Pokémon (names + URLs) from the /pokemon endpoint.
    """
    url = f"{API_BASE}/pokemon?limit={limit}&offset=0"
    logger.info(f"Fetching the list of the first {limit} Pokémon")
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])
    logger.info(f"{len(results)} Pokémon found in the list")
    return results


def fetch_pokemon_details(pokemon_url: str) -> dict:
    """
    Fetch the full details of a Pokémon from its URL.
    """
    response = requests.get(pokemon_url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def extract_data() -> str:
    """
    Main function called by Airflow.

    Returns:
        The path of the raw JSON file written.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    extracted_at = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_file = DATA_DIR / f"{today}.json"

    # 1. Pokémon list
    pokemon_list = fetch_pokemon_list()

    raw = {
        "extracted_at": extracted_at,
        "source": API_BASE,
        "count": 0,
        "pokemons": [],
    }

    errors = []
    success_count = 0

    # 2. Details of each Pokémon
    for i, entry in enumerate(pokemon_list, start=1):
        name = entry["name"]
        url = entry["url"]
        try:
            details = fetch_pokemon_details(url)
            raw["pokemons"].append(details)
            success_count += 1
            logger.info(f"[{i}/{len(pokemon_list)}] {name} fetched")
            time.sleep(SLEEP_BETWEEN_REQUESTS)
        except requests.RequestException as e:
            logger.error(f"Failed for {name}: {e}")
            errors.append(name)

    # 3. Check: at least 50 % success, otherwise fail
    if success_count < len(pokemon_list) / 2:
        raise RuntimeError(
            f"Extraction failed: only {success_count}/{len(pokemon_list)} Pokémon fetched"
        )

    raw["count"] = success_count
    raw["errors"] = errors

    # 4. Write the file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    logger.info(f"Raw file written: {output_file}")
    logger.info(f"Summary: {success_count} Pokémon OK, {len(errors)} failures")

    return str(output_file)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    path = extract_data()
    print(f"\nExtraction done: {path}")