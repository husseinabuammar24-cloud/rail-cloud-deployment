import logging
import os
import pyodbc
import requests
import azure.functions as func
from datetime import datetime

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

IRAIL_URL = "https://api.irail.be/liveboard/"


def get_connection():
    conn_str = os.environ["SQL_CONNECTION_STRING"]
    return pyodbc.connect(conn_str)


def fetch_liveboard(station_name="Brussel-Centraal"):
    params = {"station": station_name, "format": "json", "lang": "en"}
    headers = {"User-Agent": "railpulse-challenge/1.0 (student project)"}
    resp = requests.get(IRAIL_URL, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


@app.route(route="LiveboardFetch")
def LiveboardFetch(req: func.HttpRequest) -> func.HttpResponse:
    station_name = req.params.get("station", "Brussel-Centraal")

    try:
        data = fetch_liveboard(station_name)
    except Exception as e:
        logging.error(f"iRail fetch failed: {e}")
        return func.HttpResponse(f"Failed to fetch iRail data: {e}", status_code=502)

    conn = get_connection()
    cursor = conn.cursor()

    station_uri = data.get("stationinfo", {}).get("id", station_name)
    cursor.execute(
        "IF NOT EXISTS (SELECT 1 FROM stations WHERE station_uri = ?) "
        "INSERT INTO stations (station_uri, station_name) VALUES (?, ?)",
        station_uri, station_uri, station_name
    )
    cursor.execute("SELECT station_id FROM stations WHERE station_uri = ?", station_uri)
    station_id = cursor.fetchone()[0]

    inserted = 0
    for dep in data.get("departures", {}).get("departure", []):
        vehicle_name = dep.get("vehicle", "UNKNOWN")
        delay_seconds = int(dep.get("delay", 0))
        scheduled_time = datetime.fromtimestamp(int(dep.get("time", 0)))
        platform = dep.get("platform", "")
        canceled = bool(int(dep.get("canceled", 0)))

        cursor.execute(
            "IF NOT EXISTS (SELECT 1 FROM vehicles WHERE vehicle_name = ?) "
            "INSERT INTO vehicles (vehicle_name) VALUES (?)",
            vehicle_name, vehicle_name
        )
        cursor.execute("SELECT vehicle_id FROM vehicles WHERE vehicle_name = ?", vehicle_name)
        vehicle_id = cursor.fetchone()[0]

        cursor.execute(
            "INSERT INTO liveboard_records "
            "(station_id, vehicle_id, scheduled_time, delay_seconds, platform, canceled) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            station_id, vehicle_id, scheduled_time, delay_seconds, platform, canceled
        )
        inserted += 1

    conn.commit()
    conn.close()

    return func.HttpResponse(f"Inserted {inserted} liveboard records for {station_name}", status_code=200)