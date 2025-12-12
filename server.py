from flask import Flask, request, jsonify
from flask_cors import CORS
from skyfield.api import load
import numpy as np
import pytz
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Skyfield setup
ts = load.timescale()
eph = load("de421.bsp")

PLANETS = {
    "sun": eph["sun"],
    "moon": eph["moon"],
    "mercury": eph["mercury"],
    "venus": eph["venus"],
    "mars": eph["mars"],
    "jupiter": eph["jupiter barycenter"],
    "saturn": eph["saturn barycenter"],
}

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

def normalize(deg):
    return deg % 360.0

def sign_index(deg):
    return int(deg // 30)

def compute_ascendant(t, lat_deg, lon_deg):
    """
    Approximate tropical Ascendant:
    - Use apparent sidereal time if available (GAST), else fallback to GMST
    - Standard formula with mean obliquity (can refine later)
    """
    # Skyfield Time has .gast on most versions; fallback to gmst if not present
    sidereal_hours = getattr(t, "gast", None)
    if sidereal_hours is None:
        sidereal_hours = t.gmst

    # Local Sidereal Time (degrees)
    lst_deg = (sidereal_hours * 15.0 + lon_deg) % 360.0
    lst = np.deg2rad(lst_deg)

    # Mean obliquity of the ecliptic (degrees)
    eps = np.deg2rad(23.4392911)
    lat = np.deg2rad(lat_deg)

    asc = np.arctan2(
        np.sin(lst),
        np.cos(lst) * np.cos(eps) - np.tan(lat) * np.sin(eps)
    )

    return normalize(np.rad2deg(asc))

@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json(force=True)

    date = data["date"]          # LOCAL date string: YYYY-MM-DD
    time = data["time"]          # LOCAL time string: HH:MM (24h)
    lat = float(data["latitude"])
    lon = float(data["longitude"])
    tz_name = data["timezone"]   # IANA, e.g. America/Detroit

    tz = pytz.timezone(tz_name)

    dt_local = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    dt_local = tz.localize(dt_local)
    dt_utc = dt_local.astimezone(pytz.utc)

    t = ts.utc(dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour, dt_utc.minute, dt_utc.second)

    earth = eph["earth"]

    planets = {}
    for name, body in PLANETS.items():
        # apparent() helps; most important fix is the (lat, lon) order below
        astrometric = earth.at(t).observe(body).apparent()

        # IMPORTANT: Skyfield returns (LATITUDE, LONGITUDE, DISTANCE)
        lat_ecl, lon_ecl, _ = astrometric.ecliptic_latlon()

        lon_deg = normalize(lon_ecl.degrees)

        planets[name] = {
            "longitude": lon_deg,
            "sign": SIGNS[sign_index(lon_deg)]
        }

    asc = compute_ascendant(t, lat, lon)
    asc_sign = sign_index(asc)

    # Whole sign houses
    for p in planets.values():
        p["house"] = ((sign_index(p["longitude"]) - asc_sign) % 12) + 1

    return jsonify({
        "ascendant": {
            "longitude": asc,
            "sign": SIGNS[asc_sign]
        },
        "planets": planets,
        "timezone": tz_name,
        "utc": dt_utc.isoformat()
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
