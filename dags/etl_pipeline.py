"""
DAG ETL Pokémon — extract + transform.
validate et load à venir.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from scripts.extract import extract_data
from scripts.transform import transform_data

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
}

with DAG(
    dag_id="etl_pokemon",
    description="Pipeline ETL Pokémon : PokeAPI → Elasticsearch",
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
        # Le chemin du fichier brut vient du XCom de extract
        op_kwargs={
            "input_file": "{{ ti.xcom_pull(task_ids='extract') }}"
        },
    )

    extract_task >> transform_task

