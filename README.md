# Automated-watering-device

Automated plant watering device

## Requirements

- Python 3.12+ (only for running without Docker)
- UV (only for running without Docker)
- Docker (optional)

Note: if you only use Docker, a local UV installation is not required.

### Install UV (Windows)

Run in the VS Code terminal (PowerShell) or in PowerShell:

- `powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"`

After installation, close and reopen the terminal (or VS Code) to refresh PATH.

### Install UV (Linux)

Run in a terminal (bash/zsh):

- `curl -LsSf https://astral.sh/uv/install.sh | sh`

After installation, close and reopen the terminal. If `uv` is not on PATH,
add it in your shell rc file (for example `~/.bashrc`):

- `export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"`

## Structure

```
.
├── .dockerignore
├── Dockerfile
├── backend/
│   ├── app/
│   │   ├── hardware/
│   │   │   └── gpio_controller.py
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── routes.py
│   │   └── schema.sql
│   ├── requirements.txt
│   └── run.py
├── docker/
│   └── entrypoint.sh
└── frontend/
    ├── app.js
    ├── config.js
    ├── index.html
    └── styles.css
```

## Backend (UV)

1. Create venv and install deps:
   - `uv venv`
   - `uv pip install -r backend/requirements.txt`
2. Initialize SQLite:
   - `uv run flask --app backend/run.py init-db`
3. Run API:
   - `uv run python backend/run.py`

Optional env vars (pins and sensors):

- `PUMP_PIN=17`
- `VALVE_PIN=27`
- `MOISTURE_CHANNELS=0,1,2`
- `DATABASE_PATH=instance/watering.db`

## Swagger UI (Flasgger)

Install:

1. `uv venv`
2. `uv pip install -r backend/requirements.txt`

Use:

1. Run the API: `uv run python backend/run.py`
2. Open Swagger UI: [http://localhost:5000/apidocs/](http://localhost:5000/apidocs/)
3. Open raw spec (JSON): [http://localhost:5000/apispec_1.json](http://localhost:5000/apispec_1.json)

## Frontend (static)

Serve with any static server from `frontend/`, for example:

- `uv run python -m http.server 8080 --directory frontend`

If served from another host, add CORS in Flask or serve frontend from Flask.

## Run locally (Windows / Ubuntu)

### Windows (PowerShell)

1. Create venv and install deps:
   - `uv venv`
   - `uv pip install -r backend/requirements.txt`
2. Initialize SQLite:
   - `uv run flask --app backend/run.py init-db`
3. Run API:
   - `uv run python backend/run.py`
4. Serve frontend (new terminal):
   - `uv run python -m http.server 8080 --directory frontend`

Open in browser:

- [http://localhost:8080](http://localhost:8080)
- [http://localhost:5000/api/health](http://localhost:5000/api/health)
- [http://localhost:5000/apidocs/](http://localhost:5000/apidocs/)

### Ubuntu (bash)

1. Create venv and install deps:
   - `uv venv`
   - `uv pip install -r backend/requirements.txt`
2. Initialize SQLite:
   - `uv run flask --app backend/run.py init-db`
3. Run API:
   - `uv run python backend/run.py`
4. Serve frontend (new terminal):
   - `uv run python -m http.server 8080 --directory frontend`

Open in browser:

- [http://localhost:8080](http://localhost:8080)
- [http://localhost:5000/api/health](http://localhost:5000/api/health)
- [http://localhost:5000/apidocs/](http://localhost:5000/apidocs/)

## API sketch

- `GET /api/health`
- `GET /api/status`
- `GET /api/moisture`
- `POST /api/pump` { "on": true }
- `POST /api/valve` { "open": true }
- `POST /api/water` { "seconds": 5, "zone": 0 }

## Hardware notes

- Pump and valve are driven as GPIO outputs.
- Soil sensors with analog output need an ADC (example: MCP3008 via SPI).
- Enable SPI on Raspberry Pi when using MCP3008.

## Docker (UV)

Build the image:

- `docker build -t watering .`

Run (frontend on :8080, API on :5000, SQLite persisted in backend/instance):

- Windows (PowerShell): `docker run --rm -p 5000:5000 -p 8080:8080 -v ${PWD}/backend/instance:/data watering`
- Ubuntu (bash): `docker run --rm -p 5000:5000 -p 8080:8080 -v $(pwd)/backend/instance:/data watering`

Optional env vars for container:

- `-e API_BASE=http://localhost:5000`
- `-e PUMP_PIN=17`
- `-e VALVE_PIN=27`
- `-e MOISTURE_CHANNELS=0,1,2`

### Docker: status, start, stop

Check if the container is running:

- `docker ps`

Check all containers (including stopped):

- `docker ps -a`

Start the app container:

- Windows (PowerShell): `docker run --rm -p 5000:5000 -p 8080:8080 -v ${PWD}/backend/instance:/data watering`
- Ubuntu (bash): `docker run --rm -p 5000:5000 -p 8080:8080 -v $(pwd)/backend/instance:/data watering`

Stop the running container (replace NAME or ID):

- `docker stop <container_name_or_id>`

See container logs (replace NAME or ID):

- `docker logs -f <container_name_or_id>`

Quick health check:

Open in browser (clickable):

- [http://localhost:8080](http://localhost:8080)
- [http://localhost:5000/api/health](http://localhost:5000/api/health)

Quick health check:

- frontend: `http://localhost:8080`
- backend: `http://localhost:5000/api/health`
