from flask import Flask, request, jsonify
from flask_cors import CORS
from forecast import run_forecast
from utils.logging import configure_logging
import logging
import os
import requests as http_requests

# ────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────
APP_VERSION = "1.0.0"
DB_SERVICE_URL = os.getenv("DB_SERVICE_URL", "").rstrip("/")
DB_TIMEOUT = 5

app = Flask(__name__)
CORS(app)
configure_logging(app)


@app.route("/health")
def health():
    return jsonify({"status": "up", "service": "param-service"}), 200


@app.route("/version")
def version():
    """Returns the application version for the Frontend to display."""
    return jsonify({"version": APP_VERSION}), 200


@app.route("/forecast", methods=["POST"])
def forecast():
    data = request.json
    lat = data.get("lat")
    lon = data.get("lon")
    prop = data.get("property", "T2M")

    # Read username from header (passed by the frontend)
    user_id = request.headers.get("X-Username", "")

    logging.info(f"Forecast request: lat={lat}, lon={lon}, prop={prop}, user={user_id or 'anonymous'}")

    try:
        result = run_forecast(lat, lon, prop, user_id=user_id)
        return jsonify(result), 200
    except Exception as e:
        logging.error(f"Prediction failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/history", methods=["GET"])
def history():
    """
    Proxy to db-service: fetch recent inference history for a user.
    Query param: ?username=<username>
    """
    username = request.args.get("username", "")
    if not username:
        return jsonify({"error": "username is required"}), 400

    if not DB_SERVICE_URL:
        return jsonify({"history": [], "note": "DB service not configured"}), 200

    try:
        resp = http_requests.get(
            f"{DB_SERVICE_URL}/inference-log/{username}",
            timeout=DB_TIMEOUT,
        )
        resp.raise_for_status()
        return jsonify(resp.json()), 200
    except Exception as e:
        logging.error(f"[Inference] History fetch failed: {e}")
        return jsonify({"error": "Could not fetch history"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
