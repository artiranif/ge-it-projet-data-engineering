"""
etl_pipeline.py
---------------
Airflow DAG for the Pokémon ETL pipeline: PokeAPI -> clean JSON -> Elasticsearch.

Tasks (chained ``extract >> transform >> validate >> load``):
    extract    fetch the 151 Gen-1 Pokémon from PokeAPI  -> data/raw/YYYY-MM-DD.json
    transform  flatten + clean the raw JSON              -> data/processed/clean.json
    validate   run the quality checks on the clean data  -> path unchanged
    load       bulk-index the clean dataset into ES      -> Elasticsearch index name

Each task passes its return value to the next one through XCom (``ti.xcom_pull``),
so the steps stay loosely coupled.

The load step is idempotent (deterministic Elasticsearch ``_id`` = Pokémon id),
so re-running an interval updates the same documents instead of duplicating them.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from scripts.extract import extract_data
from scripts.transform import transform_data
from scripts.validate import validate_data
from scripts.load import load_data

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
}

with DAG(
    dag_id="etl_pokemon",
    description="Pokémon ETL pipeline: PokeAPI -> Elasticsearch",
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

    transform_task = PythonOperator(
        task_id="transform",
        python_callable=transform_data,
        # The raw file path comes from the extract XCom
        op_kwargs={
            "input_file": "{{ ti.xcom_pull(task_ids='extract') }}"
        },
    )

    validate_task = PythonOperator(
        task_id="validate",
        python_callable=validate_data,
        op_kwargs={
            "input_file": "{{ ti.xcom_pull(task_ids='transform') }}"
        },
    )

    load_task = PythonOperator(
        task_id="load",
        python_callable=load_data,
        op_kwargs={
            "input_file": "{{ ti.xcom_pull(task_ids='validate') }}"
        },
    )

    extract_task >> transform_task >> validate_task >> load_task

