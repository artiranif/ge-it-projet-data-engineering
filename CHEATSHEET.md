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

A `.env` file (copy of the versioned `.env.mock`) is required before starting the stack.
It must define `AIRFLOW_UID`, `ELASTIC_PASSWORD`, `KIBANA_PASSWORD` and `KIBANA_ENCRYPTION_KEY`.

> **`AIRFLOW_UID` must stay `50000`** (the user baked into the official image). Using your
> host uid requires the Airflow **entrypoint** to run on every service (to create the user and
> set `HOME=/home/airflow`); bypassing it causes `ModuleNotFoundError: No module named 'airflow'`.

The stack runs a **custom Airflow image** (`Dockerfile`, based on `apache/airflow:3.3.2`)
that installs `requirements.txt` **once, at build time** (`pip install -r requirements.txt`).
This is the official recommended practice; the Compose `_PIP_ADDITIONAL_REQUIREMENTS`
variable is not used (it is a dev-only, fragile, restart-every-time mechanism).

### Build or rebuild the image

Run this **after any change to `requirements.txt`**:

```powershell
docker compose build
docker compose build --no-cache   # force a clean rebuild
```

### Start / stop the stack

```powershell
docker compose up -d --build
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
| `airflow-logs` (named volume) | `/opt/airflow/logs` |
| `./plugins` | `/opt/airflow/plugins` |
| `./config` | `/opt/airflow/config` |

> `logs/` is a **named volume**, not a bind mount: this avoids UID/permission clashes
> between the host and the container user. Logs are still shipped to Elasticsearch.

> `PYTHONPATH=/opt/airflow` and `DATA_DIR=/opt/airflow/data/raw`, so `from scripts.extract import extract_data` works in the DAGs.

### Run a script inside the container

```powershell
docker compose exec airflow-scheduler python /opt/airflow/scripts/extract.py
```

---

## 6. Security

**No secret is stored in `docker-compose.yaml` (public repo).** All of them come from `.env`
(git-ignored): `AIRFLOW_UID`, `AIRFLOW_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`,
`ELASTIC_PASSWORD`, `KIBANA_PASSWORD`, `KIBANA_ENCRYPTION_KEY` (see `.env.mock`).

### Change the Airflow admin password

```powershell
# interactive (password not kept in the shell history)
docker compose exec airflow-apiserver airflow users reset-password --username admin

# or non-interactive
docker compose exec airflow-apiserver airflow users reset-password --username admin --password "NewStrongPassword!"

# list users
docker compose exec airflow-apiserver airflow users list
```

> Use a running service (`airflow-apiserver`, `airflow-scheduler`, `airflow-worker`).
> NOT `airflow-cli`: it is behind the `debug` profile and is not started by default.

### Change the Postgres password

The volume keeps the old password, so also update it **inside** Postgres:

```powershell
# 1. edit POSTGRES_PASSWORD in .env, then:
docker compose exec airflow-postgres psql -U airflow -c "ALTER USER airflow WITH PASSWORD 'NewStrongPassword!'"
# 2. recreate the Airflow services so they use the new connection string
docker compose up -d
```

### If secrets were already pushed to Git

Treat them as compromised: **rotate** them (above), then remove them from the history
(`git filter-repo` or BFG), force-push, and enable GitHub secret scanning +
push protection. Making the repo private is also recommended.

---

## 7. Quick troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'airflow'` | `AIRFLOW_UID` changed away from 50000 while a service bypasses the Airflow entrypoint (`entrypoint: /bin/bash`) → user/HOME not created | set `AIRFLOW_UID=50000` in `.env`, then `docker compose down && docker compose up -d` (see §5) |
| `Permission denied: '/opt/airflow/logs/...'` | `./logs` bind-mounted and not writable by the container user | use the named volume `airflow-logs` (already configured) or `chown` the folder |
| `ModuleNotFoundError: No module named 'requests'` | dependency not installed / wrong interpreter | re-run the install command (§1) with `.venv\Scripts\python.exe` |
| `UnicodeEncodeError: 'charmap' codec...` | cp1252 console on the `✅` | `$env:PYTHONIOENCODING = "utf-8"` (§3) |
| `RuntimeError: Extraction failed...` | fewer than 50 % of Pokémon fetched (network) | check the Internet connection and re-run |
| `requests.exceptions.Timeout` | PokeAPI slow / network | re-run; the timeout is 15 s per request |
