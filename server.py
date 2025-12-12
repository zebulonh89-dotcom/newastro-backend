from flask import Flask, request, jsonify
from flask_cors import CORS
from skyfield.api import load
import numpy as np
import pytz
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Load ephemeris once
ts = load.timescale()
eph = load('de421.bsp')

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

def normalize(deg):
    return deg % 360

def sign_index(deg):
    return int(deg // 30)

def compute_ascendant(time, lat, lon):
    # Local apparent sidereal time (degrees)
    lst = (time.gmst * 15 + lon) % 360
    lst = np.deg2rad(lst)

    # Mean obliquity of the ecliptic
    eps = np.deg2rad(23.4392911)
    lat = np.deg2rad(lat)

    asc = np.arctan2(
        np.sin(lst),
        np.cos(lst) * np.cos(eps) - np.tan(lat) * np.sin(eps)
    )

    return normalize(np.rad2deg(asc))

@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json()

    dt = datetime.strptime(
        f"{data['date']} {data['time']}",
        "%Y-%m-%d %H:%M"
    )
    dt = pytz.utc.localize(dt)

    t = ts.utc(
        dt.year, dt.month, dt.day,
        dt.hour, dt.minute, dt.second
    )

    earth = eph["earth"]

    planets = {}

    for name, body in PLANETS.items():
        astrometric = earth.at(t).observe(body)
        lon, lat, dist = astrometric.ecliptic_latlon()
        lon = normalize(lon.degrees)

        planets[name] = {
            "longitude": lon,
            "sign": SIGNS[sign_index(lon)]
        }

    asc = compute_ascendant(t, data["latitude"], data["longitude"])
    asc_sign = sign_index(asc)

    # Whole sign houses
    for p in planets.values():
        p["house"] = ((sign_index(p["longitude"]) - asc_sign) % 12) + 1

    return jsonify({
        "ascendant": {
            "longitude": asc,
            "sign": SIGNS[asc_sign]
        },
        "planets": planets
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
