"""
db_service.py  — MongoDB Database Microservice
Port: 5004 (ClusterIP inside Kubernetes)

Responsibilities:
  - Store / retrieve users (username, hashed password, role, has_llm_access, access_requested)
  - Store / retrieve bounded inference history (last MAX_HISTORY entries per user)
  - Expose /metrics for Prometheus-style monitoring
"""

import os
import logging
import time
from datetime import datetime, timezone

import bcrypt
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

# ────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/weatherdb")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))
APP_VERSION = "1.0.0"

# ────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
# Flask App
# ────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# ────────────────────────────────────────────────────────────
# MongoDB Connection
# ────────────────────────────────────────────────────────────
_mongo_client = None
_db = None


def get_db():
    """Lazy singleton MongoDB connection."""
    global _mongo_client, _db
    if _db is None:
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _db = _mongo_client.get_default_database()
        _ensure_indexes(_db)
    return _db


def _ensure_indexes(db):
    """Create indexes on startup for performance."""
    db.users.create_index("username", unique=True)
    db.inference_logs.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)])
    logger.info("[DB] Indexes ensured on users.username and inference_logs.(user_id, timestamp)")


# ────────────────────────────────────────────────────────────
# Simple in-process metrics counters
# ────────────────────────────────────────────────────────────
_metrics = {
    "requests_total": 0,
    "user_creates": 0,
    "user_reads": 0,
    "user_updates": 0,
    "user_deletes": 0,
    "inference_log_writes": 0,
    "inference_log_reads": 0,
    "errors_total": 0,
}


def inc(key):
    _metrics[key] = _metrics.get(key, 0) + 1


# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────

def _clean_user(doc):
    """Return user dict safe for JSON (strip Mongo _id and password_hash)."""
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    return doc


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ────────────────────────────────────────────────────────────
# Health / Version / Metrics
# ────────────────────────────────────────────────────────────

@app.before_request
def count_request():
    inc("requests_total")


@app.route("/health")
def health():
    logger.info("[DB] Health check called")
    try:
        get_db().command("ping")
        return jsonify({"status": "up", "service": "db-service", "mongo": "connected"}), 200
    except Exception as e:
        logger.error(f"[DB] Mongo ping failed: {e}")
        return jsonify({"status": "degraded", "service": "db-service", "error": str(e)}), 503


@app.route("/version")
def version():
    return jsonify({"version": APP_VERSION}), 200


@app.route("/metrics")
def metrics():
    """Prometheus-style plaintext metrics."""
    lines = [
        "# HELP db_requests_total Total HTTP requests received",
        "# TYPE db_requests_total counter",
        f"db_requests_total {_metrics['requests_total']}",
        "",
        "# HELP db_user_creates_total User creation operations",
        "# TYPE db_user_creates_total counter",
        f"db_user_creates_total {_metrics['user_creates']}",
        "",
        "# HELP db_user_reads_total User read operations",
        "# TYPE db_user_reads_total counter",
        f"db_user_reads_total {_metrics['user_reads']}",
        "",
        "# HELP db_user_updates_total User update operations",
        "# TYPE db_user_updates_total counter",
        f"db_user_updates_total {_metrics['user_updates']}",
        "",
        "# HELP db_user_deletes_total User delete operations",
        "# TYPE db_user_deletes_total counter",
        f"db_user_deletes_total {_metrics['user_deletes']}",
        "",
        "# HELP db_inference_log_writes_total Inference log write operations",
        "# TYPE db_inference_log_writes_total counter",
        f"db_inference_log_writes_total {_metrics['inference_log_writes']}",
        "",
        "# HELP db_inference_log_reads_total Inference log read operations",
        "# TYPE db_inference_log_reads_total counter",
        f"db_inference_log_reads_total {_metrics['inference_log_reads']}",
        "",
        "# HELP db_errors_total Total errors encountered",
        "# TYPE db_errors_total counter",
        f"db_errors_total {_metrics['errors_total']}",
    ]
    return "\n".join(lines), 200, {"Content-Type": "text/plain; charset=utf-8"}


# ────────────────────────────────────────────────────────────
# User Endpoints
# ────────────────────────────────────────────────────────────

@app.route("/users", methods=["POST"])
def create_user():
    """
    Create a new user.
    Body: { username, password, role, has_llm_access, access_requested }
    Password is accepted plain-text here and hashed before storage.
    If password is already hashed (starts with $2b$), store as-is.
    """
    t0 = time.time()
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "user")
    has_llm_access = bool(data.get("has_llm_access", False))
    access_requested = bool(data.get("access_requested", False))

    if not username or not password:
        inc("errors_total")
        return jsonify({"error": "username and password required"}), 400

    # Hash only if not already hashed (for seeding from users.json with plain text)
    if password.startswith("$2b$") or password.startswith("$2a$"):
        password_hash = password
    else:
        password_hash = _hash_password(password)

    doc = {
        "username": username,
        "password_hash": password_hash,
        "role": role,
        "has_llm_access": has_llm_access,
        "access_requested": access_requested,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        get_db().users.insert_one(doc)
        inc("user_creates")
        logger.info(f"[DB] User created: {username} (role={role}) in {(time.time()-t0)*1000:.1f}ms")
        return jsonify({"message": "user created", "username": username}), 201
    except DuplicateKeyError:
        inc("errors_total")
        return jsonify({"error": "User already exists"}), 400
    except Exception as e:
        inc("errors_total")
        logger.error(f"[DB] create_user error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/users", methods=["GET"])
def list_users():
    """Return all users (for admin panel). Strips password_hash."""
    t0 = time.time()
    try:
        docs = list(get_db().users.find({}, {"password_hash": 0, "_id": 0}))
        inc("user_reads")
        logger.info(f"[DB] list_users: {len(docs)} users in {(time.time()-t0)*1000:.1f}ms")
        return jsonify({"users": docs}), 200
    except Exception as e:
        inc("errors_total")
        logger.error(f"[DB] list_users error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/users/pending", methods=["GET"])
def list_pending():
    """Return usernames with access_requested=True and has_llm_access=False."""
    try:
        docs = list(get_db().users.find(
            {"access_requested": True, "has_llm_access": False},
            {"username": 1, "_id": 0}
        ))
        usernames = [d["username"] for d in docs]
        inc("user_reads")
        logger.info(f"[DB] list_pending: {len(usernames)} pending users")
        return jsonify({"users": usernames}), 200
    except Exception as e:
        inc("errors_total")
        logger.error(f"[DB] list_pending error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/users/<username>", methods=["GET"])
def get_user(username):
    """Fetch a user document (includes has_llm_access, access_requested). Strips password_hash."""
    t0 = time.time()
    try:
        doc = get_db().users.find_one({"username": username}, {"_id": 0})
        inc("user_reads")
        if not doc:
            return jsonify({"error": "User not found"}), 404
        logger.info(f"[DB] get_user: {username} in {(time.time()-t0)*1000:.1f}ms")
        return jsonify(_clean_user(doc)), 200
    except Exception as e:
        inc("errors_total")
        logger.error(f"[DB] get_user error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/users/<username>", methods=["PUT"])
def update_user(username):
    """
    Partial update of a user document.
    Body: any subset of user fields to update (e.g. has_llm_access, access_requested, role).
    """
    t0 = time.time()
    data = request.json or {}
    # Prevent overwriting username via update
    data.pop("username", None)
    data.pop("_id", None)

    if not data:
        return jsonify({"error": "No fields to update"}), 400

    try:
        result = get_db().users.update_one(
            {"username": username},
            {"$set": data}
        )
        inc("user_updates")
        if result.matched_count == 0:
            return jsonify({"error": "User not found"}), 404
        logger.info(f"[DB] update_user: {username} fields={list(data.keys())} in {(time.time()-t0)*1000:.1f}ms")
        return jsonify({"status": "updated"}), 200
    except Exception as e:
        inc("errors_total")
        logger.error(f"[DB] update_user error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/users/<username>", methods=["DELETE"])
def delete_user(username):
    """Delete a user by username."""
    t0 = time.time()
    try:
        result = get_db().users.delete_one({"username": username})
        inc("user_deletes")
        if result.deleted_count == 0:
            return jsonify({"error": "User not found"}), 404
        logger.info(f"[DB] delete_user: {username} in {(time.time()-t0)*1000:.1f}ms")
        return jsonify({"status": "deleted"}), 200
    except Exception as e:
        inc("errors_total")
        logger.error(f"[DB] delete_user error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/users/<username>/verify", methods=["POST"])
def verify_password(username):
    """
    Verify a user's password. Used by auth service at login.
    Body: { password: <plain text> }
    Returns: { valid: true/false, role, has_llm_access, access_requested }
    """
    t0 = time.time()
    data = request.json or {}
    plain = data.get("password", "")

    try:
        doc = get_db().users.find_one({"username": username})
        inc("user_reads")
        if not doc:
            return jsonify({"valid": False, "error": "User not found"}), 404

        valid = check_password(plain, doc.get("password_hash", ""))
        logger.info(f"[DB] verify_password: {username} valid={valid} in {(time.time()-t0)*1000:.1f}ms")
        if valid:
            return jsonify({
                "valid": True,
                "role": doc.get("role", "user"),
                "has_llm_access": doc.get("has_llm_access", False),
                "access_requested": doc.get("access_requested", False),
            }), 200
        else:
            return jsonify({"valid": False}), 401
    except Exception as e:
        inc("errors_total")
        logger.error(f"[DB] verify_password error: {e}")
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────────────────────
# Inference Log Endpoints
# ────────────────────────────────────────────────────────────

@app.route("/inference-log", methods=["POST"])
def log_inference():
    """
    Store one inference log entry for a user.
    Body: { user_id, model_name, lat, lon }
    Automatically removes oldest entries when count exceeds MAX_HISTORY.
    """
    t0 = time.time()
    data = request.json or {}
    user_id = data.get("user_id", "").strip()
    model_name = data.get("model_name", "")
    lat = data.get("lat")
    lon = data.get("lon")

    if not user_id:
        inc("errors_total")
        return jsonify({"error": "user_id is required"}), 400

    doc = {
        "user_id": user_id,
        "model_name": model_name,
        "lat": lat,
        "lon": lon,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        db = get_db()
        db.inference_logs.insert_one(doc)

        # Enforce bounded history: keep only the latest MAX_HISTORY entries per user
        all_entries = list(
            db.inference_logs.find(
                {"user_id": user_id},
                {"_id": 1}
            ).sort("timestamp", DESCENDING)
        )

        if len(all_entries) > MAX_HISTORY:
            ids_to_delete = [e["_id"] for e in all_entries[MAX_HISTORY:]]
            db.inference_logs.delete_many({"_id": {"$in": ids_to_delete}})
            logger.info(f"[DB] log_inference: pruned {len(ids_to_delete)} old entries for {user_id}")

        inc("inference_log_writes")
        logger.info(f"[DB] log_inference: {user_id} model={model_name} in {(time.time()-t0)*1000:.1f}ms")
        return jsonify({"status": "logged"}), 201
    except Exception as e:
        inc("errors_total")
        logger.error(f"[DB] log_inference error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/inference-log/<user_id>", methods=["GET"])
def get_inference_history(user_id):
    """Return last MAX_HISTORY inference logs for a given user_id, newest first."""
    t0 = time.time()
    try:
        docs = list(
            get_db().inference_logs.find(
                {"user_id": user_id},
                {"_id": 0}
            ).sort("timestamp", DESCENDING).limit(MAX_HISTORY)
        )
        inc("inference_log_reads")
        logger.info(f"[DB] get_history: {user_id} → {len(docs)} entries in {(time.time()-t0)*1000:.1f}ms")
        return jsonify({"history": docs}), 200
    except Exception as e:
        inc("errors_total")
        logger.error(f"[DB] get_history error: {e}")
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────────────────────
# Entrypoint
# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info(f"[DB] Starting db-service v{APP_VERSION} on port 5004")
    logger.info(f"[DB] Mongo URI: {MONGO_URI}")
    logger.info(f"[DB] Max history per user: {MAX_HISTORY}")
    app.run(host="0.0.0.0", port=5004)
