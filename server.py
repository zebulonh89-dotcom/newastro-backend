from flask import Flask, request, jsonify
from flask_cors import CORS

from skyfield.api import load
import swisseph as swe

import numpy as np
import pytz
from datetime import datetime

# --------------------------------------------------
# App setup
# --------------------------------------------------
app = Flask(__name__)
CORS(app)

# --------------------------------------------------
# Skyfield setup (PLANETS ONLY)
# --------------------------------------------------
ts = load.timescale()
eph = load("de421.bsp")

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

# --------------------------------------------------
# Swiss Ephemeris setup (ASC ONLY)
# --------------------------------------------------
swe.set_ephe_path("./ephe")
swe.set_sid_mode(swe.SIDM_FAGAN_BRADLEY)  # ignored for tropical, but keeps swe happy

def normalize(deg):
    return deg % 360

def sign_from_longitude(lon):
    return SIGNS[int(lon // 30)]

# --------------------------------------------------
# ROUTE
# --------------------------------------------------
@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json()

    # -----------------------------
    # Parse input (LOCAL time!)
    # -----------------------------
    local_dt = datetime.strptime(
        f"{data['date']} {data['time']}",
        "%Y-%m-%d %H:%M"
    )

    # timezone REQUIRED from frontend
    tz = pytz.timezone(data["timezone"])
    local_dt = tz.localize(local_dt)

    # Convert to UTC
    utc_dt = local_dt.astimezone(pytz.utc)

    # -----------------------------
    # Skyfield time (UTC)
    # -----------------------------
    t = ts.utc(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_dt.hour,
        utc_dt.minute,
        utc_dt.second
    )

    earth = eph["earth"]

    planets = {}

    for name, body in PLANETS.items():
        astrometric = earth.at(t).observe(body)
        lon, lat, dist = astrometric.ecliptic_latlon()
        lon = normalize(lon.degrees)

        planets[name] = {
            "longitude": lon,
            "sign": sign_from_longitude(lon)
        }

    # --------------------------------------------------
    # Swiss Ephemeris ASCENDANT (THE IMPORTANT PART)
    # --------------------------------------------------
    # Convert UTC datetime → Julian Day (UT)
    jd_ut = swe.julday(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0
    )

    lat = data["latitude"]
    lon = data["longitude"]

    # Houses calculation (Placidus just to extract ASC)
    houses, ascmc = swe.houses(jd_ut, lat, lon)

    asc = normalize(ascmc[0])
    asc_sign_index = int(asc // 30)

    # --------------------------------------------------
    # Whole Sign Houses
    # --------------------------------------------------
    for p in planets.values():
        p["house"] = ((int(p["longitude"] // 30) - asc_sign_index) % 12) + 1

    # --------------------------------------------------
    # RESPONSE
    # --------------------------------------------------
    return jsonify({
        "ascendant": {
            "longitude": asc,
            "sign": SIGNS[asc_sign_index]
        },
        "planets": planets,
        "meta": {
            "timezone": data["timezone"],
            "utcDateTime": utc_dt.isoformat()
        }
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
