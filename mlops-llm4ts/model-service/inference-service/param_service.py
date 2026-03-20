from flask import Flask, request, jsonify
from flask_cors import CORS
from forecast import run_forecast
from utils.logging import configure_logging
import logging
#
# --- CONFIGURATION ---
APP_VERSION = "1.0.0"

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
    
    # Basic logging of the request
    # Note: In a microservice mesh, the auth service might pass a user token header
    # which we would log here. For now, we just log the params.
    logging.info(f"Forecast request: lat={lat}, lon={lon}, prop={prop}")
    
    try:
        result = run_forecast(lat, lon, prop)
        return jsonify(result), 200
    except Exception as e:
        logging.error(f"Prediction failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Param service might run on a different port if running locally side-by-side
    # but in a pod it would likely still use 5000 (mapped to something else externally)
    # We'll use 5001 default for local testing convenience to avoid conflict with Auth
    app.run(host="0.0.0.0", port=5001)
