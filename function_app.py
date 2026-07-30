import logging
import os
import pyodbc
import requests
import azure.functions as func
from datetime import datetime

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

IRAIL_URL = "https://api.irail.be/v1/liveboard"


def get_connection():
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        raise ValueError("Environment variable 'SQL_CONNECTION_STRING' is not set.")
    return pyodbc.connect(conn_str)


# ---------------------------------------------------------
# ADDED / UPDATED USER-AGENT HEADER HERE
# ---------------------------------------------------------
def fetch_liveboard(station_name: str) -> dict:
    params = {"station": station_name, "format": "json", "lang": "en"}
    headers = {
        "User-Agent": "RailPulse-BeCode/1.0 (student.project@becode.org)"
    }
    resp = requests.get(IRAIL_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


@app.route(route="liveboardfetch")
def LiveboardFetch(req: func.HttpRequest) -> func.HttpResponse:
    station_name = req.params.get("station", "Brussel-Centraal")

    # 1. Fetch liveboard from iRail API
    try:
        data = fetch_liveboard(station_name)
    except Exception as e:
        logging.error(f"iRail fetch failed: {e}")
        return func.HttpResponse(f"iRail API Error: {e}", status_code=502)

    # 2. Connect to Azure SQL Database
    try:
        conn = get_connection()
        cursor = conn.cursor()
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return func.HttpResponse(f"SQL Database Connection Error: {e}", status_code=500)

    # 3. Process and Insert Records
    try:
        station_uri = data.get("stationinfo", {}).get("id", station_name)
        cursor.execute(
            "IF NOT EXISTS (SELECT 1 FROM stations WHERE station_uri = ?) "
            "INSERT INTO stations (station_uri, station_name) VALUES (?, ?)",
            (station_uri, station_uri, station_name)
        )
        cursor.execute("SELECT station_id FROM stations WHERE station_uri = ?", (station_uri,))
        station_id = cursor.fetchone()[0]

        inserted = 0
        for dep in data.get("departures", {}).get("departure", []):
            vehicle_name = dep.get("vehicle", "UNKNOWN")
            delay_seconds = int(dep.get("delay", 0))
            scheduled_time = datetime.fromtimestamp(int(dep.get("time", 0)))
            platform = str(dep.get("platform", ""))
            canceled = str(dep.get("canceled", "0")).strip() == "1"

            cursor.execute(
                "IF NOT EXISTS (SELECT 1 FROM vehicles WHERE vehicle_name = ?) "
                "INSERT INTO vehicles (vehicle_name) VALUES (?)",
                (vehicle_name, vehicle_name)
            )
            cursor.execute("SELECT vehicle_id FROM vehicles WHERE vehicle_name = ?", (vehicle_name,))
            vehicle_id = cursor.fetchone()[0]

            cursor.execute(
                "INSERT INTO liveboard_records "
                "(station_id, vehicle_id, scheduled_time, delay_seconds, platform, canceled) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (station_id, vehicle_id, scheduled_time, delay_seconds, platform, canceled)
            )
            inserted += 1

        conn.commit()
        conn.close()

        return func.HttpResponse(f"Inserted {inserted} liveboard records for {station_name}", status_code=200)

    except Exception as e:
        logging.error(f"SQL execution error: {e}")
        return func.HttpResponse(f"SQL Execution Error: {e}", status_code=500)