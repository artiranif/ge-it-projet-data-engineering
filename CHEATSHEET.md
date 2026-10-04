# Cheat-sheet — Data Engineering project (Pokémon / PokeAPI)

> ⚠️ For now, only the extraction step (`scripts/extract.py`) is documented here.
> The other steps (transform, load, validate, Airflow DAG) will be added later.
> Everything can run either locally (§1-§4) or inside Docker/Airflow (§5).

---

## 1. Prerequisites: virtual environment

From the project root (`ge-it-projet-data-engineering/`):

### Create the venv (once)

```powershell
python -m venv .venv
```

### Install the dependencies

```powershell
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> Dependencies are listed in `requirements.txt` (currently: `requests`).
> No need to activate the venv: calling `.venv\Scripts\python.exe` directly is enough.

---

## 2. Run the extraction

```powershell
.venv\Scripts\python.exe scripts\extract.py
```

- Fetches the first **151 Pokémon** (Gen 1) from `https://pokeapi.co/api/v2`.
- Writes the raw JSON to `data/raw/YYYY-MM-DD.json` (today's date in UTC, folder created automatically).
- Prints at the end: `✅ Extraction done: <file path>`.

---

## 3. Options / customization

### Change the output folder

`extract.py` reads the `DATA_DIR` environment variable (default: `data/raw`).

```powershell
$env:DATA_DIR = "data\raw\test"
.venv\Scripts\python.exe scripts\extract.py
```

### Force UTF-8 in the console (avoids the `UnicodeEncodeError` on ✅)

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe scripts\extract.py
```

### Call it as a function (from any Python code)

```python
from scripts.extract import extract_data
path = extract_data()   # returns the written file path (usable as an Airflow XCom)
print(path)
```

---

## 4. Check the result

```powershell
Get-ChildItem data\raw
Get-Content (Get-ChildItem data\raw\*.json | Select-Object -First 1).FullName -TotalCount 20
```

---

## 5. Run inside Docker / Airflow

A `.env` file with `ELASTIC_PASSWORD`, `KIBANA_PASSWORD` and `KIBANA_ENCRYPTION_KEY`
is required before starting the stack.

The stack uses the **official images as-is** (`apache/airflow:3.3.2`, no local `Dockerfile` / `docker build`).
Python dependencies are installed at startup by Airflow via the
`_PIP_ADDITIONAL_REQUIREMENTS` env var → it currently lists `apache-airflow-providers-elasticsearch` and `requests`.

### Start / stop the stack

```powershell
docker compose up -d
docker compose ps
docker compose logs -f airflow-scheduler
docker compose down
```

- Airflow UI: http://localhost:8016 (login `admin` / `admin`)
- Kibana: http://localhost:8017 — Elasticsearch: http://localhost:9200

### Mounted folders (host ⇄ container)

| Host | Container |
|---|---|
| `./dags` | `/opt/airflow/dags` |
| `./scripts` | `/opt/airflow/scripts` |
| `./data` | `/opt/airflow/data` |
| `./logs` | `/opt/airflow/logs` |
| `./plugins` | `/opt/airflow/plugins` |
| `./config` | `/opt/airflow/config` |

> `PYTHONPATH=/opt/airflow` and `DATA_DIR=/opt/airflow/data/raw`, so `from scripts.extract import extract_data` works in the DAGs.

### Run a script inside the container

```powershell
docker compose exec airflow-scheduler python /opt/airflow/scripts/extract.py
```

---

## 6. Quick troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'requests'` | dependency not installed / wrong interpreter | re-run the install command (§1) with `.venv\Scripts\python.exe` |
| `UnicodeEncodeError: 'charmap' codec...` | cp1252 console on the `✅` | `$env:PYTHONIOENCODING = "utf-8"` (§3) |
| `RuntimeError: Extraction failed...` | fewer than 50 % of Pokémon fetched (network) | check the Internet connection and re-run |
| `requests.exceptions.Timeout` | PokeAPI slow / network | re-run; the timeout is 15 s per request |
