# 📋 RailPulse Azure Pipeline: Session Reference & Execution Log

**Date:** July 30, 2026
**Project:** RailPulse Cloud Deployment (SNCB Liveboard ETL)
**Status:** 🟢 Fully Operational (`HTTP 200 OK` Verified)

---

## 1. Cloud Infrastructure Overview

| Resource Type | Resource Name | Region | Configuration / SKU |
| :--- | :--- | :--- | :--- |
| **Resource Group** | `rg-railpulse-challenge` | France Central | Single containment boundary |
| **Function App** | `func-railpulse-etl-hussein` | France Central | Python 3.11, Flex Consumption Plan |
| **SQL Server** | `railpulse-srv-west.database.windows.net` | Sweden Central | Admin: `dbadmin`, Minimal TLS 1.2 |
| **SQL Database** | `railpulse-db` | Sweden Central | Serverless General Purpose (Auto-pause: 1 hr) |

---

## 2. Issues Encountered & How They Were Resolved

### Issue 1: Deployment package couldn't find `host.json`
- **Symptom:** GitHub Actions / Deployment Center failed with `InvalidPackageContentException: Cannot find required host.json file at root level in the .zip package.`
- **Root Cause:** Function code lived inside a `function/` subfolder while Azure expects `host.json` at the repo root.
- **Fix:** Restructured the repo, moving `host.json`, `function_app.py`, `requirements.txt`, `.funcignore` to repo root; removed the now-empty `function/` folder.

### Issue 2: OIDC federated identity login failure
- **Symptom:** `AADSTS700213: No matching federated identity record found for presented assertion subject...`
- **Root Cause:** GitHub's federated identity subject included org/repo internal ID suffixes that didn't match the credential Azure had on file; the education tenant likely restricted regenerating Entra ID app registrations via Portal reconnect.
- **Fix:** Abandoned OIDC login entirely. Switched to **publish-profile** authentication — downloaded the Function App's publish profile, stored it as a GitHub Actions secret (`AZURE_FUNCTIONAPP_PUBLISH_PROFILE`), and updated the workflow's deploy step to use `publish-profile` instead of `azure/login@v2`.

### Issue 3: Flex Consumption plan deployment mismatch
- **Symptom:** `Error: Failed to deploy web package to App Service. Not Found (CODE: 404)` from Kudu.
- **Root Cause:** The Function App runs on the newer **Flex Consumption** plan, which needs explicit parameters in `azure/functions-action@v1` that aren't set by default.
- **Fix:** Added `sku: 'flexconsumption'` and `remote-build: 'true'` to the deploy step, letting Azure build dependencies (including `pyodbc`) server-side.

### Issue 4: iRail API service-wide outage
- **Symptom:** Every liveboard request (`Brussel-Centraal`, `Antwerpen-Centraal`) returned `{"exception":"NullPointerException","message":null,...}` with HTTP 500, for hours.
- **Root Cause:** Bug on iRail's backend, unrelated to this project. Confirmed via direct `curl` tests against multiple stations.
- **Resolution:** Waited it out; unblocked once iRail's service recovered. This also validated the function's error handling — it caught the upstream failure and returned a clean `502 Bad Gateway` instead of crashing.

### Issue 5: SQL Authentication Failure (`Error 28000 / 18456`)
- **Symptom:** Ingest endpoint returned `HTTP 500 Internal Server Error` with message: `Login failed for user 'dbadmin'. (18456)`.
- **Root Cause:** The Function App's `SQL_CONNECTION_STRING` environment variable contained a placeholder string (`Pwd=YOUR_ACTUAL_PASSWORD`) instead of the active database password.
- **Resolution Steps:**
  1. Reset the `dbadmin` password on `railpulse-srv-west` via Azure CLI.
  2. Updated `SQL_CONNECTION_STRING` in the Function App configuration with the real password.
  3. Restarted the Function App to force the process to reload the new environment variable.

### Issue 6: SQL Query Column Name Mismatches in Azure Query Editor
- **Symptom 1:** `SELECT TOP 50 * FROM liveboard_records ORDER BY created_at DESC;` failed with `Invalid column name 'created_at'`.
- **Fix 1:** The timestamp column in `liveboard_records` is actually named **`fetched_at`**.
- **Symptom 2:** JOIN query using `s.name` failed with `Invalid column name 'name'`.
- **Fix 2:** The station name column in `stations` is actually named **`station_name`**.

---

## 3. Exact Commands Executed

### Reset SQL Server Admin Password
```bash
az sql server update \
  --name railpulse-srv-west \
  --resource-group rg-railpulse-challenge \
  --admin-password "Nikihussu1423"
```

### Set Function App Environment Variable
```bash
az functionapp config appsettings set \
  --name func-railpulse-etl-hussein \
  --resource-group rg-railpulse-challenge \
  --settings SQL_CONNECTION_STRING="Driver={ODBC Driver 18 for SQL Server};Server=tcp:railpulse-srv-west.database.windows.net,1433;Database=railpulse-db;Uid=dbadmin;Pwd=Nikihussu1423;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60;ConnectRetryCount=3;ConnectRetryInterval=10;"
```

### Restart Function App Process
```bash
az functionapp restart \
  --name func-railpulse-etl-hussein \
  --resource-group rg-railpulse-challenge
```

### Trigger & Test the Ingestion Endpoint
```bash
curl -i "https://func-railpulse-etl-hussein-a3avdgapc9a8aqhg.francecentral-01.azurewebsites.net/api/liveboardfetch?station=Leuven"
```

**Confirmed output:**
```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8

Inserted 27 liveboard records for Leuven
```

---

## 4. Confirmed Database Schema Structure (3NF)

### `stations`
- `station_id` (INT, PK)
- `station_name` (VARCHAR)
- `station_uri` (VARCHAR)

### `vehicles`
- `vehicle_id` (INT, PK)
- `vehicle_name` (VARCHAR)

### `liveboard_records` (Fact Table)
- `record_id` (INT, PK, Auto-increment)
- `station_id` (INT, FK → `stations.station_id`)
- `vehicle_id` (INT, FK → `vehicles.vehicle_id`)
- `scheduled_time` (DATETIME)
- `delay_seconds` (INT)
- `platform` (VARCHAR)
- `canceled` (BIT)
- `fetched_at` (DATETIME)

---

## 5. Working SQL Verification Query

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

## 6. Deployment Method Evolution

1. Started with **GitHub Actions + OIDC login** (Deployment Center default) — blocked by Entra ID federated identity issue on the student tenant.
2. Switched to **GitHub Actions + publish-profile auth** — got past login, hit Flex Consumption 404.
3. Added **Flex Consumption parameters** to the GitHub Actions workflow — deployment succeeded.
4. Also used **`func azure functionapp publish`** (Azure Functions Core Tools CLI) directly from the terminal for faster iteration once the initial pipeline was proven — this became the primary method for pushing code fixes (User-Agent header, route casing, error handling) during live debugging.

---

## 7. Project Artifacts Generated

- **`README.md`** — production-grade project documentation covering mission, architecture diagram, 3NF schema rationale, cost-optimization settings, environment security, and deployment log.
- **`SESSION_REFERENCE.md`** (this file) — chronological debugging log for reuse in future sessions or similar Azure challenges.
