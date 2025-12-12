from flask import Flask, request, jsonify
from flask_cors import CORS
from skyfield.api import load, Topos
import pytz
from datetime import datetime

app = Flask(__name__)
CORS(app)

# -----------------------
# Skyfield setup
# -----------------------
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

# -----------------------
# Helpers
# -----------------------
def normalize(deg):
    return deg % 360

def sign_index(deg):
    return int(deg // 30)

# -----------------------
# Ascendant (correct)
# -----------------------
def compute_ascendant(t, lat, lon):
    observer = eph["earth"] + Topos(
        latitude_degrees=lat,
        longitude_degrees=lon
    )

    # Due east on horizon
    east = observer.at(t).from_altaz(
        alt_degrees=0,
        az_degrees=90
    )

    lon_ecl, lat_ecl, _ = east.ecliptic_latlon()
    return normalize(lon_ecl.degrees)

# -----------------------
# API
# -----------------------
@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json(force=True)

    date = data["date"]
    time = data["time"]
    lat = float(data["latitude"])
    lon = float(data["longitude"])
    tz_name = data["timezone"]

    tz = pytz.timezone(tz_name)

    # Build LOCAL datetime
    dt_local = datetime.strptime(
        f"{date} {time}",
        "%Y-%m-%d %H:%M"
    )
    dt_local = tz.localize(dt_local)

    # Convert to UTC ONCE
    dt_utc = dt_local.astimezone(pytz.UTC)

    # Skyfield time (UTC)
    t = ts.utc(
        dt_utc.year,
        dt_utc.month,
        dt_utc.day,
        dt_utc.hour,
        dt_utc.minute,
        dt_utc.second
    )

    earth = eph["earth"]

    # -----------------------
    # Planets (FIXED)
    # -----------------------
    planets = {}

    for name, body in PLANETS.items():
        apparent = earth.at(t).observe(body).apparent()
        lon_ecl, lat_ecl, _ = apparent.ecliptic_latlon()

        lon_deg = normalize(lon_ecl.degrees)

        planets[name] = {
            "longitude": lon_deg,
            "sign": SIGNS[sign_index(lon_deg)]
        }

    # -----------------------
    # Ascendant
    # -----------------------
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
