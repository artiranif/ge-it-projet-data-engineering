# Commands reference — Data Engineering project (Pokémon / PokeAPI)

> This is the **detailed** reference (with explanations, rationale and troubleshooting).
> For a short, copy-paste cheat-sheet of the everyday commands, see **`CHEATSHEET.md`**.
>
> ⚠️ Documented so far: `extract.py`, `transform.py`, `validate.py`, `load.py` and the Docker/Airflow stack.
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

> Dependencies are listed in `requirements.txt` (`requests`, `pandas`, `elasticsearch`).
> No need to activate the venv: calling `.venv\Scripts\python.exe` directly is enough.

---

## 2. Run the pipeline

The pipeline runs in four steps: **extract → transform → validate → load**.

### 2.1 Extraction (`extract.py`)

```powershell
.venv\Scripts\python.exe scripts\extract.py
```

- Fetches the first **151 Pokémon** (Gen 1) from `https://pokeapi.co/api/v2`.
- Writes the raw JSON to `data/raw/YYYY-MM-DD.json` (today's date in UTC, folder created automatically).
- Returns (and prints) the written file path, usable as an Airflow XCom.

### 2.2 Transformation (`transform.py`)

```powershell
.venv\Scripts\python.exe scripts\transform.py
```

- Reads today's raw file `data/raw/YYYY-MM-DD.json` (override the input folder with `RAW_DIR`, or pass an explicit path).
- Flattens the nested JSON, drops duplicates on `id`, casts types, computes `stat_total` / `power_tier`, sorts by `id`.
- Writes the clean dataset to `data/processed/clean.json` and prints its path.

Optional — transform a specific raw file:

```powershell
.venv\Scripts\python.exe -c "from scripts.transform import transform_data; print(transform_data('data/raw/2026-10-06.json'))"
```

### 2.3 Validation (`validate.py`)

```powershell
.venv\Scripts\python.exe scripts\validate.py
```

- Reads `data/processed/clean.json` (override the folder with `PROCESSED_DIR`, or pass an explicit path).
- Runs quality checks: file exists, dataset non-empty, **≥ 100 rows**, non-null and unique `id`,
  required fields present (`name`, `type_primary`, `stat_total`, `power_tier`), all six stats in
  `[1, 255]`, `stat_total` equals the sum of the stats, and every `power_tier` is one of
  `low` / `mid` / `high` / `elite`.
- Prints `Validation OK: <path>` on success. On the first failed check it raises a `ValueError`
  and exits with a non-zero code — in Airflow this marks the task **failed** and triggers a retry.
- Returns the path **unchanged**, so it can be chained via XCom to the load step.

Optional — validate a specific file:

```powershell
.venv\Scripts\python.exe -c "from scripts.validate import validate_data; print(validate_data('data/processed/clean.json'))"
```

### 2.4 Loading (`load.py`)

```powershell
.venv\Scripts\python.exe scripts\load.py
```

- Reads `data/processed/clean.json` (override the folder with `PROCESSED_DIR`, or pass an explicit path).
- Connects to Elasticsearch with this priority:
  1. the Airflow Connection **`elasticsearch_default`** — **only if you created it**
     (`airflow connections add`). This project's stack does **not** create it (ES remote
     logging uses the `[elasticsearch]` section, not a Connection);
  2. the **`ES_HOST`** env var (the effective path here — see below);
  3. the built-in default `http://localhost:9200` (CLI only).
- Creates the index if it does not exist, using the mapping in `elasticsearch/mapping.json`
  (override with `MAPPING_FILE`).
- Bulk-indexes every document with a **deterministic `_id` (the Pokémon `id`)** → the load is
  **idempotent**: re-running the DAG updates the same documents instead of creating duplicates.
- Raises `RuntimeError` if any document fails; returns the index name (default `pokemon`, override
  with `ES_INDEX`) so it can be chained via XCom.

Optional — load a specific file:

```powershell
.venv\Scripts\python.exe -c "from scripts.load import load_data; print(load_data('data/processed/clean.json'))"
```

> **Where does `ES_HOST` come from?** `load.py` reads `ES_HOST` at import time. On the host you
> set it (`$env:ES_HOST = "http://localhost:9200"`). **Inside the containers it must be declared
> as an environment variable in `docker-compose.yaml`** (`ES_HOST: 'http://elastic:${ELASTIC_PASSWORD}@airflow-elasticsearch:9200'`)
> — the variables of `.env` are **never injected** into the containers (Compose only uses `.env`
> for `${...}` substitution of the YAML). Without it, the Airflow run falls back to
> `http://localhost:9200` → `localhost` inside the container is the container itself →
> `ConnectionError`. Same principle as `DATA_DIR`.

---

## 3. Options / customization

### Change the input / output folders

Each step reads its own environment variable (all default to the project's `data/` folders):

| Step | Variable | Default |
|---|---|---|
| `extract.py` | `DATA_DIR` | `data/raw` |
| `transform.py` | `RAW_DIR` | `data/raw` |
| `transform.py` | `PROCESSED_DIR` | `data/processed` |
| `validate.py` | `PROCESSED_DIR` | `data/processed` |
| `load.py` | `PROCESSED_DIR` | `data/processed` |
| `load.py` | `MAPPING_FILE` | `elasticsearch/mapping.json` |
| `load.py` | `ES_INDEX` | `pokemon` |
| `load.py` | `ES_HOST` | `http://elastic:****@airflow-elasticsearch:9200` (set in `docker-compose.yaml`, not read from `.env`) |

```powershell
$env:DATA_DIR = "data\raw\test"
.venv\Scripts\python.exe scripts\extract.py

$env:RAW_DIR = "data\raw\test"
$env:PROCESSED_DIR = "data\processed\test"
.venv\Scripts\python.exe scripts\transform.py
.venv\Scripts\python.exe scripts\validate.py

$env:ES_INDEX = "pokemon_test"
$env:ES_HOST = "http://localhost:9200"
.venv\Scripts\python.exe scripts\load.py
```

### Force UTF-8 in the console (avoids the `UnicodeEncodeError`)

The cp1252 Windows console cannot print every non-ASCII character (emoji, accented letters,
Pokémon names, etc.). Set the encoding when a script logs such output:

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe scripts\extract.py
```

### Call them as functions (from any Python code or a DAG)

```python
from scripts.extract import extract_data
from scripts.transform import transform_data
from scripts.validate import validate_data
from scripts.load import load_data

raw = extract_data()                 # -> data/raw/YYYY-MM-DD.json
clean = transform_data(raw)          # -> data/processed/clean.json
checked = validate_data(clean)       # -> same path, unchanged (validation only)
index = load_data(checked)           # -> "pokemon" (indexed in Elasticsearch)
```

Each function returns a value (file path, then index name), so they chain naturally through
Airflow XComs (`op_kwargs={"input_file": "{{ ti.xcom_pull(task_ids='extract') }}"}`).

---

## 4. Check the result

```powershell
Get-ChildItem data\raw
Get-Content (Get-ChildItem data\raw\*.json | Select-Object -First 1).FullName -TotalCount 20

Get-ChildItem data\processed
Get-Content data\processed\clean.json -TotalCount 20

# Inspect what was indexed in Elasticsearch
curl.exe -u elastic:<ELASTIC_PASSWORD> "http://localhost:9200/pokemon/_count?pretty"
curl.exe -u elastic:<ELASTIC_PASSWORD> "http://localhost:9200/pokemon/_search?size=3&pretty"
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
| `./elasticsearch` | `/opt/airflow/elasticsearch` |
| `airflow-logs` (named volume) | `/opt/airflow/logs` |
| `./plugins` | `/opt/airflow/plugins` |
| `./config` | `/opt/airflow/config` |

> `./elasticsearch` is mounted so `load.py` can read `mapping.json`
> (`PROJECT_ROOT/elasticsearch/mapping.json`, i.e. `/opt/airflow/elasticsearch/mapping.json`).
> Without it, the `load` task fails with `FileNotFoundError`. The path must match
> **host folder name ⇒ container path** (`PROJECT_ROOT` = parent of `scripts/`).

> `logs/` is a **named volume**, not a bind mount: this avoids UID/permission clashes
> between the host and the container user. Logs are still shipped to Elasticsearch.

> `PYTHONPATH=/opt/airflow` and `DATA_DIR=/opt/airflow/data/raw`, so `from scripts.extract import extract_data` works in the DAGs.

### Task logs in Elasticsearch

For the Airflow UI to display task logs when remote logging to Elasticsearch is on, **all**
of the following are required:

| Setting | Value | Why |
|---|---|---|
| `AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER` | `elasticsearch://` | Routes the remote log backend to the ES provider (Airflow ≥ 3.3). Do **not** put an index name here. |
| `AIRFLOW__ELASTICSEARCH__HOST` | `http://elastic:${ELASTIC_PASSWORD}@airflow-elasticsearch:9200` | Credentials **must be in the URL** — there is no `[elasticsearch] user`/`password` option. |
| `AIRFLOW__ELASTICSEARCH__WRITE_TO_ES` | `True` | Without it, logs are never written to ES and the UI shows an empty log stream. |
| `AIRFLOW__ELASTICSEARCH__JSON_FORMAT` | `True` | Required for `write_to_es` to work. |
| `AIRFLOW__ELASTICSEARCH__WRITE_STDOUT` | `False` | Use ES instead of stdout. |
| `AIRFLOW__ELASTICSEARCH__TARGET_INDEX` | `airflow-logs` | Index that receives the log documents. |

> **Why the logs were empty:** with only `REMOTE_LOGGING=True` + a host, the ES handler is
> registered as the log **reader** but nothing writes to ES (`write_to_es` was unset). The
> reader then reports *“Log … not found in Elasticsearch”* and the UI shows no lines.
>
> Note: in Airflow 3, worker logs reach Elasticsearch only **after the task finishes**
> (they may be buffered until then). Reload the log page once the task is `success`/`failed`.

### Run a script inside the container

```powershell
docker compose exec airflow-scheduler python /opt/airflow/scripts/extract.py       # extract
docker compose exec airflow-scheduler python /opt/airflow/scripts/transform.py     # transform
docker compose exec airflow-scheduler python /opt/airflow/scripts/validate.py      # validate
docker compose exec airflow-scheduler python /opt/airflow/scripts/load.py          # load into Elasticsearch
docker compose exec airflow-scheduler pip show elasticsearch                      # check the ES client is installed
```

### Execution API (worker ↔ api-server)

In Airflow 3 the Celery worker runs the task through the **Internal Execution API** on the
api-server (`/execution/`). Two settings are required in a multi-container stack:

| Setting | Value | Why |
|---|---|---|
| `AIRFLOW__CORE__EXECUTION_API_SERVER_URL` | `http://airflow-apiserver:8080/execution/` | If unset it is **derived from `AIRFLOW__API__BASE_URL`** (`https://airflow.python-community.com`). The worker would then try to reach the api-server through the public NGINX URL, which can fail/time out → the task never reports back. |
| `AIRFLOW__API_AUTH__JWT_SECRET` | a single shared secret | If unset, **each container generates its own** `jwt_secret.generated`; task tokens are rejected by the api-server. |

> Generate the shared secret with `secrets.token_urlsafe(32)` (256-bit, cryptographically
> secure — the Python-doc recommended way). It belongs in `.env` (git-ignored), never
> hardcoded in `docker-compose.yaml`:
>
> ```powershell
> .venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
> ```
>
> Then set `AIRFLOW_JWT_SECRET=<the generated value>` in `.env`. For hardened deployments,
> Airflow recommends asymmetric keys (`api_auth.jwt_private_key_path` + `trusted_jwks_url`).

There is also a **second** shared secret, `AIRFLOW__API__SECRET_KEY` (`[api] secret_key`).
It signs the requests the UI makes back to the worker to read **live** task logs. It must be
identical on every component too — otherwise the worker answers `403` and the log view shows:

```
!!!! Please make sure that all your Airflow components ... have the same
'secret_key' configured in '[api]' section ...
*** Log ... not found in Elasticsearch ...
```

Set it from `.env` as well: `AIRFLOW_API_SECRET_KEY=<a shared random value>`.

> Symptom when one of these is missing: the task stays in `queued` / `up for retry` and the
> audit log shows *“Executor CeleryExecutor reported that the task instance … finished with
> state failed, but the task instance's state attribute is queued”*.

### Task logs: how Airflow chooses what to show

For a failed task, the UI reads logs by `try_number`. If the run has **no `try_number == 1` attempt**
(e.g. the task was queued/retried without ever running) the UI prints *“No logs available for
this task.”* — this is **not** a problem with `scripts/extract.py`. Once the execution-API issue
above is fixed and a real attempt runs, the logs appear (shipped to Elasticsearch).

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

### Full reset (nuclear)

Destroys **everything**: containers, the custom image, and ALL data volumes
(Postgres metadata + Elasticsearch indices). Use it to start from a clean slate.

```powershell
docker compose down -v --remove-orphans --rmi local
docker volume ls | Select-String airflow   # check leftovers, then: docker volume rm <name>
docker compose build --no-cache
docker compose up -d
```

After this, `airflow-init` recreates the DB schema and the admin user from `.env`.

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
| Task logs empty in the UI (*“Log … not found in Elasticsearch”*) | ES handler active but nothing written to ES (`WRITE_TO_ES`/`JSON_FORMAT` unset) | set `AIRFLOW__ELASTICSEARCH__WRITE_TO_ES=True` + `JSON_FORMAT=True` and `REMOTE_BASE_LOG_FOLDER=elasticsearch://` (see §5) |
| ES `401 Unauthorized` / no logs indexed | credentials missing from the host URL | put `user:pass@` in `AIRFLOW__ELASTICSEARCH__HOST` (no `[elasticsearch]` user/password option exists) |
| Logs appear only after the task finishes | Airflow 3 flushes worker logs to ES at task end | expected behaviour — reload once the task is done |
| `ModuleNotFoundError: No module named 'requests'` | dependency not installed / wrong interpreter | re-run the install command (§1) with `.venv\Scripts\python.exe` |
| Task stuck in `up for retry` + audit log *“finished with state failed, but the task instance's state attribute is queued”* | worker cannot reach the Internal Execution API (URL derived from the public `API__BASE_URL` via NGINX) and/or the JWT secret is not shared | set `AIRFLOW__CORE__EXECUTION_API_SERVER_URL=http://airflow-apiserver:8080/execution/` and a shared `AIRFLOW__API_AUTH__JWT_SECRET` (see §5) |
| `docker` not recognized in PowerShell | Docker Desktop not running / not on `PATH` | start Docker Desktop, then `docker compose ps` |
| Log view shows *“Please make sure that all your Airflow components … have the same 'secret_key' configured in '[api]' section”* | `AIRFLOW__API__SECRET_KEY` unset (each container generated its own) → worker returns `403` for live logs | set a shared `AIRFLOW__API__SECRET_KEY` in `.env` (see §5), then `docker compose up -d` |
| `UnicodeEncodeError: 'charmap' codec...` | cp1252 console on non-ASCII output (emoji, accented letters, Pokémon names) | `$env:PYTHONIOENCODING = "utf-8"` (§3) |
| `ValueError: Quality check failed: ...` (from `validate.py`) | one of the quality checks failed on `data/processed/clean.json` | inspect the printed message, re-run `transform.py`, then `validate.py` again |
| `ModuleNotFoundError: No module named 'elasticsearch'` | the ES client is not installed in the image / venv | reinstall the dependencies (§1), then `docker compose build && docker compose up -d` (see §5) |
| `ConnectionError` / `elastic_transport.ConnectionError` (from `load.py`) | inside a container, `ES_HOST` is unset → it falls back to `http://localhost:9200` (the container itself) | declare `ES_HOST` in `docker-compose.yaml` (`http://elastic:${ELASTIC_PASSWORD}@airflow-elasticsearch:9200`); on the host, set `$env:ES_HOST` |
| `elasticsearch.NotFoundError` / mapping error (from `load.py`) | index created with an incompatible mapping | delete the index (`curl.exe -X DELETE -u elastic:<pw> http://localhost:9200/<ES_INDEX>`) and re-run `load.py` |
| `FileNotFoundError: .../elasticsearch/mapping.json` (from `load.py`, inside Docker) | the `elasticsearch/` folder is not mounted into the container | declare `./elasticsearch:/opt/airflow/elasticsearch` in `docker-compose.yaml`, then `docker compose up -d` (see §5) |
| `RuntimeError: ... documents failed during the bulk` | some documents were rejected by Elasticsearch (mapping/type mismatch) | check the up-to-3 errors logged above it, fix the mapping or the data, then re-run |
| `RuntimeError: Extraction failed...` | fewer than 50 % of Pokémon fetched (network) | check the Internet connection and re-run |
| `requests.exceptions.Timeout` | PokeAPI slow / network | re-run; the timeout is 15 s per request |
