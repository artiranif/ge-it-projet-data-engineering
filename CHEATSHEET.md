# Cheat-sheet — Pokémon / PokeAPI pipeline

> Short reference: one command per line, with a one-line description.
> Full explanations, rationale and troubleshooting live in **`COMMANDS.md`**.

Run everything from the project root (`ge-it-projet-data-engineering/`).

---

## 1. Setup (local)

```powershell
python -m venv .venv                                      # create the virtual environment (once)
.venv\Scripts\python.exe -m pip install --upgrade pip     # upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt   # install the dependencies
```

---

## 2. Run the pipeline (local)

```powershell
.venv\Scripts\python.exe scripts\extract.py      # fetch the 151 Gen-1 Pokémon -> data/raw/YYYY-MM-DD.json
.venv\Scripts\python.exe scripts\transform.py    # flatten + clean the raw JSON -> data/processed/clean.json
.venv\Scripts\python.exe scripts\validate.py     # run the quality checks on clean.json (fails on the first error)
```

> `load.py` is not implemented yet.

---

## 3. Inspect the data (local)

```powershell
Get-ChildItem data\raw              # list the raw files
Get-ChildItem data\processed        # list the processed files
Get-Content data\processed\clean.json -TotalCount 20   # preview the clean dataset
```

---

## 4. Environment variables

```powershell
$env:PYTHONIOENCODING = "utf-8"    # force UTF-8 in the console (avoids UnicodeEncodeError)
$env:DATA_DIR = "data\raw\test"    # override the extract output folder (default: data/raw)
$env:RAW_DIR = "data\raw\test"     # override the transform input folder (default: data/raw)
$env:PROCESSED_DIR = "data\processed\test"   # override the transform output / validate input folder (default: data/processed)
```

---

## 5. Docker / Airflow

```powershell
cp .env.mock .env                  # create .env from the versioned template (first time only)
docker compose build               # rebuild the image (after any change to requirements.txt)
docker compose up -d               # start the stack (recreates containers, keeps the volumes)
docker compose up -d --build       # rebuild + start in one command
docker compose ps                  # list the running services
docker compose logs -f airflow-scheduler   # follow the scheduler logs
docker compose down                # stop the stack (KEEPS the data volumes)
```

---

## 6. Run a script inside a container

```powershell
docker compose exec airflow-scheduler python /opt/airflow/scripts/extract.py      # run extract in the container
docker compose exec airflow-scheduler python /opt/airflow/scripts/transform.py    # run transform in the container
docker compose exec airflow-scheduler python /opt/airflow/scripts/validate.py     # run validate in the container
docker compose exec airflow-scheduler pip show <package>                           # check an installed dependency
```

---

## 7. Maintenance & security

```powershell
docker compose exec airflow-apiserver airflow users list                                          # list the Airflow users
docker compose exec airflow-apiserver airflow users reset-password --username admin              # reset the admin password
docker compose exec airflow-postgres psql -U airflow -c "ALTER USER airflow WITH PASSWORD '...'" # change the Postgres password
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"                    # generate a shared secret for .env
```

---

## 8. Full reset (⚠️ DELETES all data)

```powershell
docker compose down -v --remove-orphans --rmi local   # remove containers, image AND all data volumes
docker compose build --no-cache                       # rebuild the image from scratch
docker compose up -d                                  # start the stack fresh
```

---

## Ports

| Service | URL |
|---|---|
| Airflow UI | http://localhost:8016 (`admin` / `admin`) |
| Kibana | http://localhost:8017 |
| Elasticsearch | http://localhost:9200 |
