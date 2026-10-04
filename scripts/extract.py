"""
extract.py
----------
Extraction des données Pokémon depuis l'API publique PokeAPI.

- Récupère la liste des 151 premiers Pokémon (Gen 1).
- Pour chaque Pokémon, récupère ses détails (types, stats, abilities...).
- Sauvegarde le JSON brut dans data/raw/YYYY-MM-DD.json
- Retourne le chemin du fichier (utilisable via XCom dans Airflow)
- Testable en CLI : python scripts/extract.py
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

# Nombre de Pokémon à récupérer (Gen 1 = 151)
POKEMON_LIMIT = 151

# Racine du projet = dossier parent de scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data" / "raw"))

REQUEST_TIMEOUT = 15
# PokeAPI n'a pas de rate limit officiel, mais on reste fair-play[reference:1]
SLEEP_BETWEEN_REQUESTS = 0.1


# ---------------------------------------------------------------------------
# Fonctions
# ---------------------------------------------------------------------------

def fetch_pokemon_list(limit: int = POKEMON_LIMIT) -> list[dict]:
    """
    Récupère la liste des Pokémon (noms + URLs) depuis l'endpoint /pokemon.
    """
    url = f"{API_BASE}/pokemon?limit={limit}&offset=0"
    logger.info(f"Récupération de la liste des {limit} premiers Pokémon")
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])
    logger.info(f"{len(results)} Pokémon trouvés dans la liste")
    return results


def fetch_pokemon_details(pokemon_url: str) -> dict:
    """
    Récupère les détails complets d'un Pokémon via son URL.
    """
    response = requests.get(pokemon_url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def extract_data() -> str:
    """
    Fonction principale appelée par Airflow.
    Retourne le chemin du fichier JSON brut écrit.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    extracted_at = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_file = DATA_DIR / f"{today}.json"

    # 1. Liste des Pokémon
    pokemon_list = fetch_pokemon_list()

    raw = {
        "extracted_at": extracted_at,
        "source": API_BASE,
        "count": 0,
        "pokemons": [],
    }

    errors = []
    success_count = 0

    # 2. Détails de chaque Pokémon
    for i, entry in enumerate(pokemon_list, start=1):
        name = entry["name"]
        url = entry["url"]
        try:
            details = fetch_pokemon_details(url)
            raw["pokemons"].append(details)
            success_count += 1
            logger.info(f"[{i}/{len(pokemon_list)}] {name} récupéré")
            time.sleep(SLEEP_BETWEEN_REQUESTS)
        except requests.RequestException as e:
            logger.error(f"Échec pour {name} : {e}")
            errors.append(name)

    # 3. Vérification : au moins 50 % de succès sinon on échoue
    if success_count < len(pokemon_list) / 2:
        raise RuntimeError(
            f"Extraction échouée : seulement {success_count}/{len(pokemon_list)} Pokémon récupérés"
        )

    raw["count"] = success_count
    raw["errors"] = errors

    # 4. Écriture du fichier
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    logger.info(f"Fichier brut écrit : {output_file}")
    logger.info(f"Résumé : {success_count} Pokémon OK, {len(errors)} échecs")

    return str(output_file)


# ---------------------------------------------------------------------------
# Exécution en CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    path = extract_data()
    print(f"\n✅ Extraction terminée : {path}")