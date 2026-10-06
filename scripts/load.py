"""
load.py
-------
Load the transformed dataset (data/processed/clean.json) into Elasticsearch.

The file is the last step of the ETL pipeline (extract -> transform -> validate
-> load). It can be run standalone from the command line, or imported and
called by Airflow through ``load_data()``.

- Creates the index if it does not exist, using the mapping defined in
  ``elasticsearch/mapping.json``.
- Bulk-loads the documents with a deterministic ``_id`` (the Pokémon ``id``)
  -> idempotent: re-running the DAG does not create duplicates.
- Uses the Airflow Connection ``elasticsearch_default`` when available,
  otherwise a default URL (handy for standalone CLI testing).

Input
-----
    data/processed/clean.json  (produced by ``scripts/transform.py``)
        A list of flat records, one per Pokémon, each containing at least an
        ``id`` field, used as the Elasticsearch document ``_id``.

Output
------
    The Elasticsearch index name (a string), so it can be chained via XCom.

Configuration
-------------
    PROCESSED_DIR  input folder        (env var ``PROCESSED_DIR``, default ``data/processed``)
    MAPPING_FILE   index mapping file  (env var ``MAPPING_FILE``,  default ``elasticsearch/mapping.json``)
    ES_INDEX       target index name   (env var ``ES_INDEX``,      default ``pokemon``)
    ES_HOST        fallback ES URL     (env var ``ES_HOST``,       default ``http://localhost:9200``)

Usage
-----
    CLI::

        python scripts/load.py

    As a function::

        from scripts.load import load_data
        index = load_data()                        # -> "pokemon"
        index = load_data("data/processed/clean.json")
"""

import json
import logging
import os
from pathlib import Path

from elasticsearch import Elasticsearch, helpers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", PROJECT_ROOT / "data" / "processed"))
MAPPING_FILE = Path(os.getenv(
    "MAPPING_FILE",
    PROJECT_ROOT / "elasticsearch" / "mapping.json"
))

INDEX_NAME = os.getenv("ES_INDEX", "pokemon")

# Default URL when there is no Airflow Connection (CLI testing)
DEFAULT_ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _get_es_client() -> Elasticsearch:
    """
    Return an Elasticsearch client. Priority:
      1. Airflow Connection "elasticsearch_default" (when Airflow is available)
      2. ``ES_HOST`` environment variable (CLI / Docker fallback)
    """
    try:
        from airflow.hooks.base import BaseHook
        conn = BaseHook.get_connection("elasticsearch_default")
        host = conn.host or DEFAULT_ES_HOST
        # conn.host may not contain the scheme, depending on how it was entered
        if not host.startswith("http"):
            host = f"http://{host}"
        if conn.port and f":{conn.port}" not in host:
            host = f"{host}:{conn.port}"
        logger.info(f"Elasticsearch connection via Airflow Connection: {host}")
        return Elasticsearch(host)
    except Exception as e:
        logger.warning(
            f"Airflow Connection unavailable ({e}). Falling back to {DEFAULT_ES_HOST}"
        )
        return Elasticsearch(DEFAULT_ES_HOST)


# ---------------------------------------------------------------------------
# Index creation
# ---------------------------------------------------------------------------

def _ensure_index(es: Elasticsearch, index: str):
    """Create the index with the mapping if it does not already exist."""
    if es.indices.exists(index=index):
        logger.info(f"Index '{index}' already exists")
        return

    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    es.indices.create(index=index, body=mapping)
    logger.info(f"Index '{index}' created with the mapping {MAPPING_FILE.name}")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _bulk_actions(df_records: list[dict], index: str):
    """
    Bulk action generator for helpers.bulk().
    _id = Pokémon id -> idempotence.
    """
    for pokemon in df_records:
        yield {
            "_index": index,
            "_id": pokemon["id"],
            "_source": pokemon,
        }


def load_data(input_file: str | None = None) -> str:
    """
    Main function called by Airflow.

    Args:
        input_file: path to the clean JSON file. Defaults to
            ``data/processed/clean.json``.

    Returns:
        The Elasticsearch index name, so it can be chained via XCom.
    """
    if input_file is None:
        input_file = PROCESSED_DIR / "clean.json"
    input_file = Path(input_file)

    if not input_file.exists():
        raise FileNotFoundError(f"File not found: {input_file}")

    # 1. Read the transformed dataset
    with open(input_file, "r", encoding="utf-8") as f:
        records = json.load(f)
    logger.info(f"{len(records)} documents read from {input_file}")

    if not records:
        raise ValueError("No document to load")

    # 2. ES connection + index creation
    es = _get_es_client()
    logger.info(f"ES cluster: {es.info().get('version', {}).get('number', '?')}")

    _ensure_index(es, INDEX_NAME)

    # 3. Manual refresh: make sure we start from a clean state before the bulk
    es.indices.refresh(index=INDEX_NAME)

    # 4. Bulk insert
    success, errors = helpers.bulk(
        es,
        _bulk_actions(records, INDEX_NAME),
        stats_only=False,
        raise_on_error=False,
    )

    logger.info(f"Bulk finished: {success} succeeded, {len(errors)} failed")

    if errors:
        # Log the first 3 errors for debugging
        for err in errors[:3]:
            logger.error(f"Bulk error: {err}")
        raise RuntimeError(f"{len(errors)} documents failed during the bulk")

    # 5. Refresh so the documents are immediately visible in Kibana
    es.indices.refresh(index=INDEX_NAME)

    count = es.count(index=INDEX_NAME)["count"]
    logger.info(f"Index '{INDEX_NAME}' now contains {count} documents")

    return INDEX_NAME


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    index = load_data()
    print(f"\nLoading done into the index '{index}'")