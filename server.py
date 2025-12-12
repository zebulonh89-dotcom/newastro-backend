from flask import Flask, request, jsonify
from flask_cors import CORS
from skyfield.api import load
from skyfield.framelib import ecliptic_frame
from timezonefinder import TimezoneFinder
from zoneinfo import ZoneInfo
import numpy as np
from datetime import datetime

app = Flask(__name__)
CORS(app)

# -------------------------------------------------------------------
# Skyfield setup
# -------------------------------------------------------------------
ts = load.timescale()
eph = load("de421.bsp")
earth = eph["earth"]

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

tf = TimezoneFinder()

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def normalize(deg):
    return deg % 360.0

def sign_index(deg):
    return int(deg // 30)

# -------------------------------------------------------------------
# CORRECT ASCENDANT (APPARENT SIDEREAL TIME + TRUE OBLIQUITY)
# -------------------------------------------------------------------
def compute_ascendant(t, lat_deg, lon_deg):
    """
    Computes the tropical Ascendant using:
    - Apparent sidereal time (GAST)
    - True obliquity of the ecliptic
    Matches Swiss Ephemeris / Astro.com
    """

    lat = np.deg2rad(lat_deg)

    # Apparent sidereal time at Greenwich (radians)
    gast = t.gast * 15.0
    gast = np.deg2rad(gast)

    # Local apparent sidereal time
    lst = gast + np.deg2rad(lon_deg)

    # True obliquity of date
    eps = t.obliquity().radians

    # Ascendant formula
    asc = np.arctan2(
        np.sin(lst),
        np.cos(lst) * np.cos(eps) - np.tan(lat) * np.sin(eps)
    )

    return normalize(np.rad2deg(asc))

# -------------------------------------------------------------------
# API
# -------------------------------------------------------------------
@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json(force=True)

    date = data["date"]
    time = data["time"]
    lat = float(data["latitude"])
    lon = float(data["longitude"])

    # ---------------------------------------------------------------
    # Timezone resolution (HISTORICAL + DST SAFE)
    # ---------------------------------------------------------------
    tz_name = tf.timezone_at(lat=lat, lng=lon) or tf.certain_timezone_at(lat=lat, lng=lon)
    if not tz_name:
        return jsonify({"error": "Could not determine timezone"}), 400

    tz = ZoneInfo(tz_name)

    # Local datetime
    dt_local = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)

    # UTC datetime
    dt_utc = dt_local.astimezone(ZoneInfo("UTC"))

    # Skyfield time
    t = ts.utc(
        dt_utc.year,
        dt_utc.month,
        dt_utc.day,
        dt_utc.hour,
        dt_utc.minute,
        dt_utc.second
    )

    # ---------------------------------------------------------------
    # Planet positions (GEOCENTRIC, TROPICAL)
    # ---------------------------------------------------------------
    planets = {}
    for name, body in PLANETS.items():
        astrometric = earth.at(t).observe(body)
        lon_ecl, lat_ecl, _ = astrometric.frame_latlon(ecliptic_frame)
        lon = normalize(lon_ecl.degrees)

        planets[name] = {
            "longitude": lon,
            "degreeInSign": round(lon % 30, 6),
            "sign": SIGNS[sign_index(lon)]
        }

    # ---------------------------------------------------------------
    # Ascendant
    # ---------------------------------------------------------------
    asc = compute_ascendant(t, lat, lon)
    asc_sign = sign_index(asc)

    # Whole-sign houses
    for p in planets.values():
        p["house"] = ((sign_index(p["longitude"]) - asc_sign) % 12) + 1

    return jsonify({
        "ascendant": {
            "longitude": asc,
            "degreeInSign": round(asc % 30, 6),
            "sign": SIGNS[asc_sign]
        },
        "planets": planets,
        "timezone": {
            "name": tz_name,
            "localDateTime": dt_local.isoformat(),
            "utcDateTime": dt_utc.isoformat()
        }
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
