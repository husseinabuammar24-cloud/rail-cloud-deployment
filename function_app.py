import logging
import os
import pyodbc
import requests
import azure.functions as func
from datetime import datetime

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

IRAIL_URL = "https://api.irail.be/v1/liveboard"

# Multi-Hub Expansion: key Belgian stations polled automatically by the timer trigger
MAJOR_HUBS = [
    "Brussel-Centraal",
    "Antwerpen-Centraal",
    "Gent-Sint-Pieters",
    "Liège-Guillemins",
]


def get_connection():
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        raise ValueError("Environment variable 'SQL_CONNECTION_STRING' is not set.")
    return pyodbc.connect(conn_str)


def fetch_liveboard(station_name: str) -> dict:
    params = {"station": station_name, "format": "json", "lang": "en"}
    headers = {
        "User-Agent": "RailPulse-BeCode/1.0 (student.project@becode.org)"
    }
    resp = requests.get(IRAIL_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def process_station(cursor, station_name: str) -> int:
    """
    Shared ETL logic for a single station: fetch, upsert station/vehicle
    lookups, and insert liveboard records idempotently. Used by both the
    HTTP trigger (manual, single station) and the Timer trigger (automated,
    loops over MAJOR_HUBS) so the insert logic only exists in one place.
    """
    data = fetch_liveboard(station_name)

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

        # Idempotency Logic: skip if this exact snapshot (station, vehicle,
        # scheduled_time) was already recorded, so repeated timer runs
        # don't create duplicate rows for the same train/time combination.
        cursor.execute(
            "SELECT 1 FROM liveboard_records "
            "WHERE station_id = ? AND vehicle_id = ? AND scheduled_time = ?",
            (station_id, vehicle_id, scheduled_time)
        )
        if cursor.fetchone():
            continue

        cursor.execute(
            "INSERT INTO liveboard_records "
            "(station_id, vehicle_id, scheduled_time, delay_seconds, platform, canceled) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (station_id, vehicle_id, scheduled_time, delay_seconds, platform, canceled)
        )
        inserted += 1

    return inserted


# ---------------------------------------------------------------------------
# HTTP Trigger — manual, single-station ingestion (existing behavior)
# ---------------------------------------------------------------------------
@app.route(route="liveboardfetch")
def LiveboardFetch(req: func.HttpRequest) -> func.HttpResponse:
    station_name = req.params.get("station", "Brussel-Centraal")

    try:
        conn = get_connection()
        cursor = conn.cursor()
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return func.HttpResponse(f"SQL Database Connection Error: {e}", status_code=500)

    try:
        inserted = process_station(cursor, station_name)
        conn.commit()
        return func.HttpResponse(
            f"Inserted {inserted} liveboard records for {station_name}", status_code=200
        )
    except requests.exceptions.RequestException as e:
        logging.error(f"iRail fetch failed: {e}")
        return func.HttpResponse(f"iRail API Error: {e}", status_code=502)
    except Exception as e:
        logging.error(f"SQL execution error: {e}")
        return func.HttpResponse(f"SQL Execution Error: {e}", status_code=500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Timer Trigger — DISABLED. Was automated every 15 minutes across MAJOR_HUBS.
# CRON format: {second} {minute} {hour} {day} {month} {day-of-week}
# ---------------------------------------------------------------------------
# @app.timer_trigger(schedule="0 */15 * * * *", arg_name="mytimer", run_on_startup=False)
def LiveboardTimer(mytimer: func.TimerRequest) -> None:
    if mytimer.past_due:
        logging.info("Timer trigger is running late.")

    logging.info("Starting scheduled liveboard ingestion across all major hubs...")

    try:
        conn = get_connection()
    except Exception as e:
        logging.error(f"Timer run aborted — database connection failed: {e}")
        return

    total_inserted = 0
    try:
        cursor = conn.cursor()
        for station in MAJOR_HUBS:
            try:
                inserted = process_station(cursor, station)
                conn.commit()
                total_inserted += inserted
                logging.info(f"  {station}: {inserted} new records")
            except requests.exceptions.RequestException as e:
                # One station's upstream failure shouldn't abort the whole run
                logging.error(f"  {station}: iRail fetch failed — {e}")
                conn.rollback()
            except Exception as e:
                logging.error(f"  {station}: SQL error — {e}")
                conn.rollback()
    finally:
        conn.close()

    logging.info(
        f"Scheduled ingestion complete — {total_inserted} new records "
        f"across {len(MAJOR_HUBS)} stations."
    )
