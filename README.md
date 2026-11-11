# Customer Complaint Management and SLA Tracking System

A full-stack demonstration system for registering and managing customer complaints, tracking assignments and messages, monitoring service-level agreements, recording resolutions, and collecting customer feedback. The application uses a FastAPI API, SQLAlchemy 2.0 with SQLite, a responsive HTML/CSS/Vanilla JavaScript frontend, and reproducible synthetic-data generators.

## Technology stack

- Python, FastAPI, Pydantic, SQLAlchemy 2.0, SQLite
- HTML, CSS, Vanilla JavaScript
- Pytest, HTTPX

## Main features

- Complaint dashboard with status, priority, and SLA metrics
- Complaint registration, search, filtering, detail, updates, and status history
- Customer and agent listing and supported create/update operations
- Complaint assignment history and message threads
- SLA breach/at-risk monitoring, event history, pause/resume, and escalation
- Resolutions, reopening, customer surveys, and satisfaction metrics
- Deterministic synthetic data generation in Starter and Full modes, with CSV/JSON/SQL exports

## Project structure

```text
backend/                 FastAPI application, routes, schemas, services, models, tests
data/                    Local SQLite database and generated exports
frontend/                Static web application (index.html, css/, js/)
generator/                Synthetic entity generators, validation, exports, and tests
data_dictionary.md       Database tables and relationships
requirements.txt         Python dependencies
README.md                Setup, operation, and test instructions
```

## Installation and environment setup

Use Python 3.10 or newer. From the repository root, create and activate a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For Command Prompt, activate with `.venv\Scripts\activate.bat`. On macOS/Linux, use `python3 -m venv .venv`, `source .venv/bin/activate`, and then install `requirements.txt`.

The app uses the local `data/complaints.db` SQLite file by default. No credentials or API keys are required. Local environment files, virtual environments, caches, and SQLite database files are excluded by `.gitignore`.

## Database initialization

For a new or already initialized local database, initialize missing tables with:

```powershell
python -m backend.init_db
```

This invokes SQLAlchemy `create_all`; it does not import synthetic data or delete existing rows. Back up important local data before changing application versions. The application does not initialize or migrate the schema automatically when the API starts.

## Synthetic dataset generation

Generators create data in memory by default. To generate and validate a Starter dataset or Full dataset:

```powershell
python -m generator.phase8 --mode starter
python -m generator.phase8 --mode full
```

To explicitly export the integrated dataset to `data/generated/`:

```powershell
python -m generator.phase8 --mode full --export
```

The pipeline uses seed `20261022`. Its generated SQL is an export artifact; the generator commands do not import records into the application database. Do not execute an export against a populated database unless you have reviewed and explicitly intend that operation. Generated exports may contain substantial synthetic data and should be reviewed before committing.

## Run the application

Open two terminals at the repository root.

Terminal 1, start the API:

```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2, serve the static frontend:

```powershell
python -m http.server 3000 --directory frontend
```

Open <http://127.0.0.1:3000>. The frontend calls the API at `http://127.0.0.1:8000`; the backend allows the local frontend origins on port 3000. API documentation is available at <http://127.0.0.1:8000/docs>, and health/readiness checks are at `/health` and `/ready`.

## API areas

The API is versioned under `/api/v1`: customers, complaints and complaint history, agents, assignments, messages, SLA monitoring, resolutions/reopening, surveys/customer satisfaction, and dashboard summary. The interactive OpenAPI page at `/docs` shows the current request and response schemas.

## Testing and validation

Run the focused backend API tests:

```powershell
python -m pytest backend/tests/test_api.py backend/tests/test_import_dataset.py -q
```

Run all backend and generator tests:

```powershell
python -m pytest backend/tests generator/tests -q
```

Check JavaScript syntax with Node.js:

```powershell
node --check frontend/js/app.js
```

The automated API and generator tests use isolated test databases. Avoid running `python -m backend.tests.test_database` against a working local database: that legacy standalone validation script inserts and removes records directly. Use the pytest commands above for routine validation.

## Data and Git safety

The application database is local user data and is ignored by Git. Dataset generation and export are separate from database import. Keep local database backups, `.env` files, and generated artifacts out of commits unless they are intentionally reviewed and suitable for sharing. The import utility has explicit safeguards and should only be used with a reviewed export and a deliberate import action.

For the complete database schema reference, see [data_dictionary.md](data_dictionary.md). Generator dataset shape, validation, and known limitations are documented in [generator/data_dictionary.md](generator/data_dictionary.md) and [generator/validation_report.md](generator/validation_report.md).
