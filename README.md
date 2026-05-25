# Automated-watering-device
Automatyczne urządzenie do podlewania roślin

## Structure
```
.
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
└── frontend/
	 ├── app.js
	 ├── index.html
	 └── styles.css
```

## Backend (Flask)
1. Create venv and install deps:
	- `python -m venv .venv`
	- `source .venv/bin/activate`
	- `pip install -r requirements.txt`
2. Initialize SQLite:
	- `flask --app run.py init-db`
3. Run API:
	- `python run.py`

Optional env vars (pins and sensors):
- `PUMP_PIN=17`
- `VALVE_PIN=27`
- `MOISTURE_CHANNELS=0,1,2`
- `DATABASE_PATH=instance/watering.db`

## Frontend (static)
Serve with any static server from `frontend/`, for example:
- `python -m http.server 8080`

If served from another host, add CORS in Flask or serve frontend from Flask.

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
