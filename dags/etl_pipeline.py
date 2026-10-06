"""
DAG ETL Pokémon — étape 1 : extraction uniquement.
On ajoutera transform / validate / load progressivement.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from scripts.extract import extract_data

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
}

with DAG(
    dag_id="etl_pokemon",
    description="Extraction PokeAPI → JSON brut",
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args=default_args,
    tags=["etl", "pokemon"],
) as dag:

    extract_task = PythonOperator(
        task_id="extract",
        python_callable=extract_data,
    )