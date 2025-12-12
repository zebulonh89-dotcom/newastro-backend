from flask import Flask, request, jsonify
from flask_cors import CORS
import swisseph as swe
import pytz
from datetime import datetime

app = Flask(__name__)
CORS(app)

# -------------------------------------------------
# Swiss Ephemeris setup
# -------------------------------------------------
# IMPORTANT: ephemeris files must be in ./ephe
swe.set_ephe_path("./ephe")

PLANETS = {
    "sun": swe.SUN,
    "moon": swe.MOON,
    "mercury": swe.MERCURY,
    "venus": swe.VENUS,
    "mars": swe.MARS,
    "jupiter": swe.JUPITER,
    "saturn": swe.SATURN,
}

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def normalize(deg):
    return deg % 360

def sign_index(deg):
    return int(deg // 30)

# -------------------------------------------------
# API
# -------------------------------------------------
@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json(force=True)

    date = data["date"]           # YYYY-MM-DD
    time = data["time"]           # HH:MM (LOCAL)
    lat = float(data["latitude"])
    lon = float(data["longitude"])
    tz_name = data["timezone"]    # e.g. America/Detroit

    # -------------------------
    # Local → UTC
    # -------------------------
    tz = pytz.timezone(tz_name)
    dt_local = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    dt_local = tz.localize(dt_local)
    dt_utc = dt_local.astimezone(pytz.utc)

    # -------------------------
    # Julian Day (UT)
    # -------------------------
    jd_ut = swe.julday(
        dt_utc.year,
        dt_utc.month,
        dt_utc.day,
        dt_utc.hour + dt_utc.minute / 60.0
    )

    # -------------------------
    # Planets (Swiss Ephemeris)
    # -------------------------
    planets = {}

    for name, pid in PLANETS.items():
        lonlat = swe.calc_ut(jd_ut, pid)[0]
        lon = normalize(lonlat[0])

        planets[name] = {
            "longitude": lon,
            "sign": SIGNS[sign_index(lon)]
        }

    # -------------------------
    # Houses + Ascendant (Swiss)
    # Whole Sign
    # -------------------------
    houses, ascmc = swe.houses_ex(jd_ut, lat, lon, b'W')
    asc = normalize(ascmc[0])
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
