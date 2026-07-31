# 🚉 RailPulse Cloud: Azure Challenge

| | |
|---|---|
| **Repository** | `railpulse-challenge-azure` |
| **Type** | Learning Challenge |
| **Duration** | 5 days |
| **Started** | July 29, 2026 |
| **Completed** | July 30, 2026 |
| **Deadline** | July 31, 2026, 5:00 PM |
| **Live Endpoint** | [func-railpulse-etl-hussein.../api/liveboardfetch](https://func-railpulse-etl-hussein-a3avdgapc9a8aqhg.francecentral-01.azurewebsites.net/api/liveboardfetch?station=Leuven) |

---

## Table of Contents

1. [Mission](#mission)
2. [Repository Structure](#repository-structure)
3. [System Architecture](#system-architecture)
4. [Cloud Infrastructure](#cloud-infrastructure)
5. [Database Schema](#database-schema)
6. [ETL Pipeline Logic](#etl-pipeline-logic)
7. [Security](#security)
8. [Cost Optimization](#cost-optimization)
9. [Verification](#verification)
10. [Roadmap](#roadmap)

---

## Mission

RailPulse is an urban mobility consulting firm building an automated ETL pipeline that pulls real-time liveboard metrics from the SNCB/iRail API, processes them in a serverless environment, and writes them into Azure SQL — structured for next week's analytics dashboards.

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
│   │ Plan: Flex Consumption (Serverless) | Runtime: Python 3.11              │   │
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
   +--------------------------+         +--------------------------+
   |       stations           |         |       vehicles           |
   +--------------------------          +--------------------------+
   | PK  station_id  (INT)    |         | PK  vehicle_id  (INT)    | 
   |     station_name(VARCHAR)|         |     vehicle_name(VARCHAR)|
   |     station_uri (VARCHAR)|         +-------------+------------+
   +-----------+--------------+                       |
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

1. **Extract** — HTTP GET to `https://api.irail.be/v1/liveboard?station={station}&format=json&lang=en`, with a custom `User-Agent` header (required by iRail to avoid intermittent 500s).
2. **Transform** — parses departures into vehicle, platform, delay, and cancellation fields; normalizes booleans and timestamps.
3. **Load** — upserts station/vehicle lookups, then inserts liveboard snapshots via parameterized `pyodbc` queries into Azure SQL.

**Live endpoint:**
```
GET https://func-railpulse-etl-hussein-a3avdgapc9a8aqhg.francecentral-01.azurewebsites.net/api/liveboardfetch?station=Leuven
```

---

## Security

- **Zero hardcoded credentials** — connection string injected via Function App Application Settings (`SQL_CONNECTION_STRING`), read via `os.environ`.
- **Encrypted transport** — `Encrypt=yes`, `TrustServerCertificate=no`, minimum TLS 1.2.
- **Firewall** — Azure SQL server allows "Azure services and resources" plus the developer's local IP for testing.

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
- [x] **Nice-to-have:** Idempotency logic — checks for an existing (station_id, vehicle_id, scheduled_time) row before inserting, so repeated timer runs never create duplicates

Both `LiveboardFetch` (HTTP) and `LiveboardTimer` (Timer) are confirmed live and Enabled in the Azure Portal Functions list.

