# 🚉 RailPulse Cloud: Azure Challenge

| | |
|---|---|
| **Repository** | `railpulse-challenge-azure` |
| **Type** | Learning Challenge |
| **Live Endpoint** | [func-railpulse-etl-hussein.../api/liveboardfetch](https://func-railpulse-etl-hussein-a3avdgapc9a8aqhg.francecentral-01.azurewebsites.net/api/liveboardfetch?station=Leuven) |

> **Note:** As of July 31, 2026, the upstream iRail API is experiencing a service-wide outage (`NullPointerException` on their end, confirmed across multiple stations and independent of this pipeline). The endpoint above will return a `502` with a clean error message rather than data until iRail recovers. See [Verification](#verification) for proof of a successful end-to-end run.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Usage](#usage)
4. [Repository Structure](#repository-structure)
5. [System Architecture](#system-architecture)
6. [Cloud Infrastructure](#cloud-infrastructure)
7. [Database Schema](#database-schema)
8. [ETL Pipeline Logic](#etl-pipeline-logic)
9. [Security](#security)
10. [Cost Optimization](#cost-optimization)
11. [Verification](#verification)
12. [Roadmap](#roadmap)
13. [Project Timeline](#project-timeline)

---

## Introduction

RailPulse is an urban mobility consulting firm building an automated ETL pipeline that pulls real-time liveboard metrics from the SNCB/iRail API, processes them in a serverless environment, and writes them into Azure SQL — structured for next week's analytics dashboards.

This project transitions a legacy, on-premise-style delay reporting workflow into a modern, cloud-native architecture: a Python Azure Function fetches live train departure data, normalizes it into a relational schema, and persists it to Azure SQL, automatically and on a schedule, at effectively zero cost within Azure's free student tier.

---

## Installation

### Prerequisites
- Python 3.11
- [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local) (`func`)
- An Azure subscription (Azure for Students works fine)
- ODBC Driver 18 for SQL Server installed locally (for local testing)

### Clone and set up locally

```bash
git clone https://github.com/husseinabuammar24-cloud/rail-cloud-deployment.git
cd rail-cloud-deployment

python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Configure local secrets

Create `local.settings.json` in the repo root (this file is gitignored and never committed):

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "SQL_CONNECTION_STRING": "Driver={ODBC Driver 18 for SQL Server};Server=tcp:railpulse-srv-west.database.windows.net,1433;Database=railpulse-db;Uid=dbadmin;Pwd=<YOUR_PASSWORD>;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60;"
  }
}
```

### Run locally

```bash
func start
```

The HTTP trigger will be available at `http://localhost:7071/api/liveboardfetch`.

### Deploy to Azure

Deployment is automated via GitHub Actions on every push to `main` (see [`.github/workflows/main_func-railpulse-etl-hussein.yml`](.github/workflows/main_func-railpulse-etl-hussein.yml)). To deploy manually instead:

```bash
func azure functionapp publish func-railpulse-etl-hussein
```

---

## Usage

### Fetch a single station's liveboard on demand

```bash
curl -i "https://func-railpulse-etl-hussein-a3avdgapc9a8aqhg.francecentral-01.azurewebsites.net/api/liveboardfetch?station=Leuven"
```

**Successful response:**
```
HTTP/1.1 200 OK

Inserted 27 liveboard records for Leuven
```

### Fetch a different station

Swap the `station` query parameter to any valid Belgian station name known to iRail:

```bash
curl -i "https://func-railpulse-etl-hussein-a3avdgapc9a8aqhg.francecentral-01.azurewebsites.net/api/liveboardfetch?station=Antwerpen-Centraal"
```

### Automated ingestion (no action needed)

The `LiveboardTimer` function runs automatically every 15 minutes and polls four major hubs (Brussel-Centraal, Antwerpen-Centraal, Gent-Sint-Pieters, Liège-Guillemins) without any manual trigger. No setup required beyond deployment — it's already running.

### Query the ingested data

Run in Azure Portal → SQL databases → `railpulse-db` → Query editor:

```sql
SELECT TOP 50
    l.record_id,
    s.station_name,
    l.vehicle_id,
    l.scheduled_time,
    l.delay_seconds,
    l.platform,
    l.canceled,
    l.fetched_at
FROM liveboard_records l
JOIN stations s ON l.station_id = s.station_id
ORDER BY l.fetched_at DESC;
```

---

## Repository Structure

```
railpulse-challenge-azure/
├── .github/
│   └── workflows/
│       └── main_func-railpulse-etl-hussein.yml   # CI/CD: builds & deploys on push to main
├── function_app.py                                # Core ETL logic (HTTP-triggered Azure Function)
├── host.json                                       # Azure Functions runtime configuration
├── requirements.txt                                 # Python dependencies for remote build
├── .funcignore                                      # Excludes .venv, __pycache__ etc. from deploy zip
├── .gitignore                                       # Keeps secrets & local artifacts out of git
├── local.settings.json                              # LOCAL ONLY — gitignored, holds dev secrets
└── README.md                                        # This file
```

| File | Required? | Purpose |
|---|---|---|
| `function_app.py` | ✅ Yes | The actual function: fetches iRail data, transforms it, writes to Azure SQL |
| `host.json` | ✅ Yes | Must sit at repo root — tells the Azure Functions runtime how to load the app. Deployment fails without it in the right place |
| `requirements.txt` | ✅ Yes | Azure's remote build step reads this to `pip install` dependencies (`azure-functions`, `requests`, `pyodbc`) server-side |
| `.funcignore` | ✅ Yes | Prevents `.venv/`, `__pycache__/`, and other local-only files from bloating the deployment package |
| `.github/workflows/*.yml` | ✅ Yes | Defines the GitHub Actions pipeline: build → zip → deploy via publish profile to the Flex Consumption Function App |
| `.gitignore` | ✅ Yes | Ensures `local.settings.json`, `.venv/`, `.python_packages/` never get committed |
| `local.settings.json` | ⚠️ Local only | Holds the SQL connection string (with password) for local testing — **never committed**, mirrored manually into Azure's Application Settings for production |
| `README.md` | ✅ Yes | Required deliverable — documents schema and architecture decisions |

**Not required / should stay out of git:**
- `.venv/` — local Python virtual environment, machine-specific
- `.python_packages/` — build artifact from local `func azure functionapp publish` runs, regenerated automatically
- `.vscode/` — editor config, harmless either way but not functionally required

---

## System Architecture

```
                           ┌──────────────────────────┐
                           │   SNCB / iRail API       │
                           │   (api.irail.be)         │
                           └────────────┬─────────────┘
                                        │ HTTP GET
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Microsoft Azure Infrastructure (Resource Group: rg-railpulse-challenge)         │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ Azure Function App (func-railpulse-etl-hussein)                         │   │
│   │ Plan: Flex Consumption (Serverless) | Runtime: Python 3.11             │   │
│   │ Region: France Central                                                  │   │
│   │                                                                         │   │
│   │   ┌─────────────────────────────────────────────────────────────────┐   │   │
│   │   │ HTTP Trigger: /api/liveboardfetch?station={station_name}        │   │   │
│   │   │  • Fetches JSON liveboard from SNCB/iRail API                   │   │   │
│   │   │  • Parses station, vehicle, platform, and delay metrics         │   │   │
│   │   │  • Connects via pyodbc / ODBC Driver 18                         │   │   │
│   │   └────────────────────────────────┬────────────────────────────────┘   │   │
│   └────────────────────────────────────┼────────────────────────────────────┘   │
│                                        │ Encrypted SQL (Port 1433)              │
│                                        ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ Azure SQL Server (railpulse-srv-west.database.windows.net)              │   │
│   │ Database: railpulse-db | Tier: Serverless (Auto-Pause 1 hr)             │   │
│   │                                                                         │   │
│   │   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │   │
│   │   │     stations     │  │     vehicles     │  │  liveboard_records   │  │   │
│   │   │ ──────────────── │  │ ──────────────── │  │ ──────────────────── │  │   │
│   │   │ PK station_id    │◄─┤ PK vehicle_id    │◄─┤ PK record_id         │  │   │
│   │   │    station_name  │  │    vehicle_name  │  │ FK station_id        │  │   │
│   │   │    station_uri   │  │                  │  │ FK vehicle_id        │  │   │
│   │   └──────────────────┘  └──────────────────┘  │    scheduled_time    │  │   │
│   │                                               │    delay_seconds     │  │   │
│   │                                               │    platform          │  │   │
│   │                                               │    canceled          │  │   │
│   │                                               │    fetched_at        │  │   │
│   │                                               └──────────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Cloud Infrastructure

| Resource Type | Resource Name | Region | Configuration / SKU |
| :--- | :--- | :--- | :--- |
| Resource Group | `rg-railpulse-challenge` | France Central | Single containment boundary — delete once to tear everything down |
| Function App | `func-railpulse-etl-hussein` | France Central | Python 3.11, Flex Consumption Plan |
| Storage Account | (LRS storage) | France Central | Standard_LRS (Locally Redundant) |
| SQL Server | `railpulse-srv-west` | Sweden Central | Minimal TLS 1.2, Public Access + Azure Services allowed |
| SQL Database | `railpulse-db` | Sweden Central | Serverless General Purpose, Auto-pause 1 hour, Max Size 2 GB |

---

## Database Schema

The schema follows **Third Normal Form (3NF)** to avoid redundancy across high-frequency time-series records.

```
   +-----------------------+              +-----------------------+
   |       stations        |              |       vehicles        |
   +-----------------------+              +-----------------------+
   | PK  station_id  (INT) |              | PK  vehicle_id  (INT) |
   |     station_name(VARCHAR)            |     vehicle_name(VARCHAR)
   |     station_uri (VARCHAR)            +-----------+-----------+
   +-----------+-----------+                          |
               |                                      |
               | 1                                    | 1
               | N                                    | N
   +-----------+--------------------------------------+---+
   |                  liveboard_records                   |
   +------------------------------------------------------+
   | PK  record_id       (INT, IDENTITY)                  |
   | FK  station_id      (INT)                            |
   | FK  vehicle_id      (INT)                            |
   |     scheduled_time  (DATETIME)                       |
   |     delay_seconds   (INT)                            |
   |     platform        (VARCHAR)                        |
   |     canceled        (BIT)                            |
   |     fetched_at      (DATETIME)                       |
   +------------------------------------------------------+
```

**`stations`** — master data for unique stations, avoiding repeated text across millions of liveboard rows.
- `station_id` (INT, PK)
- `station_name` (VARCHAR(100), NOT NULL) — e.g. `Leuven`, `Brussel-Centraal`
- `station_uri` (VARCHAR(255), UNIQUE) — canonical ID from the iRail API

**`vehicles`** — unique train/vehicle identifiers.
- `vehicle_id` (INT, PK)
- `vehicle_name` (VARCHAR(100), UNIQUE NOT NULL) — e.g. `BE.NMBS.IC1831`

**`liveboard_records`** — fact table capturing point-in-time train status snapshots.
- `record_id` (INT, PK, IDENTITY)
- `station_id` (INT, FK → `stations.station_id`)
- `vehicle_id` (INT, FK → `vehicles.vehicle_id`)
- `scheduled_time` (DATETIME2, NOT NULL)
- `delay_seconds` (INT, DEFAULT 0)
- `platform` (VARCHAR(20))
- `canceled` (BIT, DEFAULT 0)
- `fetched_at` (DATETIME2, DEFAULT GETUTCDATE()) — ingestion timestamp

---

## ETL Pipeline Logic

`function_app.py` implements a single HTTP-triggered function, `LiveboardFetch`, in three explicit stages so failures are attributable to the right layer:

1. **Extract** — `fetch_liveboard()` sends a GET to `https://api.irail.be/v1/liveboard`, with `station`, `format=json`, `lang=en` as query params and a custom `User-Agent: RailPulse-BeCode/1.0 (student.project@becode.org)` header (required by iRail — generic/missing User-Agents intermittently trigger 500s on their end). A 15s timeout guards against hangs. Failures here return `502 Bad Gateway` with the upstream error message.

2. **Connect** — `get_connection()` reads `SQL_CONNECTION_STRING` from environment variables and opens a `pyodbc` connection. Missing config raises immediately with a clear message. Failures here return `500` with the connection error, distinguishing DB issues from API issues.

3. **Transform & Load** — for each departure:
   - Upserts the station (`IF NOT EXISTS ... INSERT`) keyed on `station_uri`, then looks up its `station_id`.
   - Upserts the vehicle keyed on `vehicle_name`, then looks up its `vehicle_id`.
   - Normalizes `delay` to int seconds, `time` (Unix epoch) to `datetime`, `platform` to string, and `canceled` to a proper boolean (`"1"` → `True`).
   - Inserts one `liveboard_records` row per departure via parameterized query.
   - Commits once per station after all departures are processed; returns `200 OK` with a count of inserted rows.

Auth level is `ANONYMOUS` — chosen deliberately for this learning challenge to simplify testing via plain `curl`/browser calls without managing function keys. For a production deployment this would be revisited (see [Roadmap](#roadmap)).

**Live endpoint:**
```
GET https://func-railpulse-etl-hussein-a3avdgapc9a8aqhg.francecentral-01.azurewebsites.net/api/liveboardfetch?station=Leuven
```

**Example success response:**
```
Inserted 27 liveboard records for Leuven
```

---

## Security

- **Zero hardcoded credentials** — connection string injected via Function App Application Settings (`SQL_CONNECTION_STRING`), read via `os.environ`.
- **Encrypted transport** — `Encrypt=yes`, `TrustServerCertificate=no`, minimum TLS 1.2.
- **Firewall** — Azure SQL server allows "Azure services and resources" plus the developer's local IP for testing.
- **Known trade-off** — the HTTP trigger uses `AuthLevel.ANONYMOUS` rather than `FUNCTION`-level keys, chosen to simplify testing during this learning challenge. A production deployment should switch back to `FUNCTION` auth (or add API Management / Entra ID auth) to prevent unauthenticated public writes to the database.

```bash
az functionapp config appsettings set \
  --name func-railpulse-etl-hussein \
  --resource-group rg-railpulse-challenge \
  --settings SQL_CONNECTION_STRING="Driver={ODBC Driver 18 for SQL Server};Server=tcp:railpulse-srv-west.database.windows.net,1433;Database=railpulse-db;Uid=dbadmin;Pwd=<SECURE_PASSWORD>;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60;ConnectRetryCount=3;ConnectRetryInterval=10;"
```

---

## Cost Optimization

| Strategy | Detail |
|---|---|
| SQL Auto-Pause | Serverless tier, 1-hour idle delay — compute stops billing when unused |
| Flex Consumption Plan | Function App only bills for actual execution time |
| Locally Redundant Storage (LRS) | Avoids costlier geo-replication |
| Single Resource Group | `rg-railpulse-challenge` holds everything for one-click teardown |

---

## Verification

```sql
SELECT TOP 50
    l.record_id,
    s.station_name,
    l.vehicle_id,
    l.scheduled_time,
    l.delay_seconds,
    l.platform,
    l.canceled,
    l.fetched_at
FROM liveboard_records l
JOIN stations s ON l.station_id = s.station_id
ORDER BY l.fetched_at DESC;
```

**Result:** `HTTP 200 OK` — *"Inserted 27 liveboard records for Leuven"*, confirmed by the join query above returning correctly linked station/vehicle/record rows.

---

## Roadmap

- [x] Provision Serverless Azure SQL & Flex Consumption Function App
- [x] Build normalized 3NF schema (`stations`, `vehicles`, `liveboard_records`)
- [x] Deploy HTTP-triggered Python Function
- [x] Verify end-to-end ingestion (iRail → Azure SQL)
- [x] Document schema and architecture in this README
- [x] **Nice-to-have:** Timer Trigger (`LiveboardTimer`, CRON `0 */15 * * * *`) for automated polling, deployed and enabled
- [x] **Nice-to-have:** Multi-hub expansion — `LiveboardTimer` polls Brussel-Centraal, Antwerpen-Centraal, Gent-Sint-Pieters, and Liège-Guillemins every run
- [x] **Nice-to-have:** Idempotency logic — checks for an existing `(station_id, vehicle_id, scheduled_time)` row before inserting, so repeated timer runs never create duplicates

Both `LiveboardFetch` (HTTP) and `LiveboardTimer` (Timer) are confirmed live and Enabled in the Azure Portal Functions list.

---

## Project Timeline
5 days


Core infrastructure (Azure SQL, Function App, schema) was provisioned and the first successful end-to-end ingestion was verified on Day 2. The remaining time was spent debugging deployment configuration (host.json placement, OIDC vs. publish-profile authentication, Flex Consumption plan parameters) and adding the automated timer trigger, multi-hub polling, and idempotency logic ahead of the Day 5 deadline.
