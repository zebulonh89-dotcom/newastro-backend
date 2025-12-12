from flask import Flask, request, jsonify
from flask_cors import CORS
from skyfield.api import load
import pytz
import numpy as np
from datetime import datetime
import traceback

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

def compute_ascendant(t, lat, lon):
    # Greenwich Apparent Sidereal Time
    gast = t.gast * 15.0  # degrees
    lst = normalize(gast + lon)

    eps = np.deg2rad(23.4392911)
    lat = np.deg2rad(lat)
    lst = np.deg2rad(lst)

    asc = np.arctan2(
        np.sin(lst),
        np.cos(lst) * np.cos(eps) - np.tan(lat) * np.sin(eps)
    )

    return normalize(np.rad2deg(asc))

# -----------------------
# Route
# -----------------------
@app.route("/calculate", methods=["POST"])
def calculate():
    try:
        data = request.get_json(force=True)

        date = data.get("date")
        time = data.get("time")
        lat = float(data.get("latitude"))
        lon = float(data.get("longitude"))
        tz_name = data.get("timezone")

        if not all([date, time, tz_name]):
            return jsonify({"error": "Missing date, time, or timezone"}), 400

        # Parse LOCAL time
        tz = pytz.timezone(tz_name)
        dt_local = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        dt_local = tz.localize(dt_local)

        # Convert to UTC
        dt_utc = dt_local.astimezone(pytz.utc)

        t = ts.utc(
            dt_utc.year,
            dt_utc.month,
            dt_utc.day,
            dt_utc.hour,
            dt_utc.minute,
            dt_utc.second
        )

        earth = eph["earth"]

        planets = {}
        for name, body in PLANETS.items():
            astrometric = earth.at(t).observe(body)
            lon_ecl, lat_ecl, _ = astrometric.ecliptic_latlon()
            lon_deg = normalize(lon_ecl.degrees)

            planets[name] = {
                "longitude": lon_deg,
                "sign": SIGNS[sign_index(lon_deg)]
            }

        asc = compute_ascendant(t, lat, lon)
        asc_sign = sign_index(asc)

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

    except Exception as e:
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500

# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
