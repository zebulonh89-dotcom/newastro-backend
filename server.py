import os
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify
from flask_cors import CORS

import numpy as np
from timezonefinder import TimezoneFinder
from skyfield.api import load
from skyfield.framelib import ecliptic_frame

# Obliquity helpers (Skyfield provides these; we keep fallback for safety)
try:
    from skyfield.nutationlib import true_obliquity_radians
except Exception:  # pragma: no cover
    true_obliquity_radians = None

app = Flask(__name__)
CORS(app)

tf = TimezoneFinder()

# Load ephemeris once (cached by Skyfield after first download)
ts = load.timescale()
eph = load("de421.bsp")

# Planets (keep keys capitalized; your frontend normalizes to lowercase)
PLANETS = {
    "Sun": eph["sun"],
    "Moon": eph["moon"],
    "Mercury": eph["mercury"],
    "Venus": eph["venus"],
    "Mars": eph["mars"],
    "Jupiter": eph["jupiter barycenter"],
    "Saturn": eph["saturn barycenter"],
}

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

def normalize_deg(deg: float) -> float:
    return deg % 360.0

def sign_index_from_lon(lon_deg: float) -> int:
    return int(normalize_deg(lon_deg) // 30)

def deg_in_sign(lon_deg: float) -> float:
    return normalize_deg(lon_deg) % 30.0

def get_iana_tz(lat: float, lon: float) -> str:
    tz_name = tf.timezone_at(lat=lat, lng=lon) or tf.certain_timezone_at(lat=lat, lng=lon)
    if not tz_name:
        raise ValueError("Could not determine IANA timezone from coordinates")
    return tz_name

def parse_local_datetime(date_str: str, time_str: str) -> datetime:
    # supports "13:54" and "13.54"
    time_str = str(time_str).strip().replace(".", ":")
    # allow optional seconds
    fmt = "%Y-%m-%d %H:%M:%S" if time_str.count(":") == 2 else "%Y-%m-%d %H:%M"
    return datetime.strptime(f"{date_str} {time_str}", fmt)

def local_to_utc(date_str: str, time_str: str, lat: float, lon: float):
    dt_local_naive = parse_local_datetime(date_str, time_str)
    tz_name = get_iana_tz(lat, lon)
    tz = ZoneInfo(tz_name)

    # Attach timezone. (fold handling for ambiguous times: default fold=0)
    dt_local = dt_local_naive.replace(tzinfo=tz)

    # Convert to UTC
    dt_utc = dt_local.astimezone(ZoneInfo("UTC"))
    return tz_name, dt_local, dt_utc

def skyfield_time_from_utc(dt_utc: datetime):
    return ts.utc(
        dt_utc.year, dt_utc.month, dt_utc.day,
        dt_utc.hour, dt_utc.minute, dt_utc.second + dt_utc.microsecond / 1e6
    )

def get_true_obliquity_rad(t):
    # Prefer true obliquity of date
    if true_obliquity_radians is not None:
        try:
            return float(true_obliquity_radians(t))
        except Exception:
            pass
    # Fallback (close enough if this ever triggers)
    return math.radians(23.4392911)

def compute_ascendant_deg(t, lat_deg: float, lon_deg: float) -> float:
    """
    Ascendant ecliptic longitude (tropical) using:
    - Local Apparent Sidereal Time (GAST)
    - True obliquity of date
    """
    # Greenwich Apparent Sidereal Time in hours -> degrees
    gast_deg = float(t.gast) * 15.0

    # Local Apparent Sidereal Time (degrees). longitude east-positive; West is negative (your inputs use negative)
    last_deg = normalize_deg(gast_deg + lon_deg)
    theta = math.radians(last_deg)

    eps = get_true_obliquity_rad(t)
    phi = math.radians(lat_deg)

    # Standard ascendant formula
    asc_rad = math.atan2(
        math.sin(theta),
        math.cos(theta) * math.cos(eps) - math.tan(phi) * math.sin(eps)
    )
    asc_deg = normalize_deg(math.degrees(asc_rad))
    return asc_deg

def planet_ecliptic_longitude_deg(t, body):
    """
    Geocentric apparent ecliptic longitude (true ecliptic of date).
    """
    earth = eph["earth"]
    astrometric = earth.at(t).observe(body).apparent()
    lat, lon, dist = astrometric.frame_latlon(ecliptic_frame)
    return normalize_deg(float(lon.degrees))

@app.get("/")
def root():
    return jsonify({"ok": True, "service": "astro-backend-skyfield"})

@app.post("/calculate")
def calculate():
    data = request.get_json(force=True) or {}

    # Accept either latitude/longitude OR lat/lon (be forgiving)
    lat = data.get("latitude", data.get("lat"))
    lon = data.get("longitude", data.get("lon"))
    date_str = data.get("date")
    time_str = data.get("time")

    if date_str is None or time_str is None or lat is None or lon is None:
        return jsonify({"error": True, "message": "Expected date, time, latitude, longitude"}), 400

    lat = float(lat)
    lon = float(lon)

    # 1) local -> utc using historical DST rules
    tz_name, dt_local, dt_utc = local_to_utc(date_str, time_str, lat, lon)

    # 2) skyfield time
    t = skyfield_time_from_utc(dt_utc)

    # 3) planets
    planets = {}
    for name, body in PLANETS.items():
        lon_deg = planet_ecliptic_longitude_deg(t, body)
        sidx = sign_index_from_lon(lon_deg)
        planets[name] = {
            "longitude": lon_deg,
            "sign": SIGNS[sidx],
            "degreeInSign": round(deg_in_sign(lon_deg), 6),
        }

    # 4) ascendant
    asc_deg = compute_ascendant_deg(t, lat, lon)
    asc_sidx = sign_index_from_lon(asc_deg)
    asc = {
        "longitude": asc_deg,
        "sign": SIGNS[asc_sidx],
        "degreeInSign": round(deg_in_sign(asc_deg), 6),
    }

    # 5) whole sign houses from ASC sign
    for p in planets.values():
        p_sidx = sign_index_from_lon(p["longitude"])
        p["house"] = ((p_sidx - asc_sidx) % 12) + 1

    return jsonify({
        "ascendant": asc,
        "planets": planets,
        "timezone": {
            "name": tz_name,
            "localDateTime": dt_local.isoformat(),
            "utcDateTime": dt_utc.isoformat(),
        },
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
