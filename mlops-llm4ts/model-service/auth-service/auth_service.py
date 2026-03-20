"""
auth_service.py — Authentication Microservice
Port: 5000

User storage: prefers DB service (MongoDB via db-service:5004).
Falls back to users.json when DB_SERVICE_URL is not set (local dev only).
LLM access control fields (has_llm_access, access_requested) live in MongoDB.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import logging
from datetime import datetime
from utils.logging import configure_logging
import db_client
from db_client import DBServiceUnavailable

# ────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────
APP_VERSION = "1.0.0"
USERS_FILE = "users.json"
AUDIT_FILE = "audit.json"

app = Flask(__name__)
CORS(app)
configure_logging(app)

DB_ENABLED = bool(os.getenv("DB_SERVICE_URL", ""))


# ────────────────────────────────────────────────────────────
# Startup: seed MongoDB from users.json if DB is empty
# ────────────────────────────────────────────────────────────

def _seed_db_from_json():
    """
    On first boot, if the DB users collection is empty, seed it from users.json.
    Plain-text passwords in the JSON are hashed by the DB service.
    """
    if not DB_ENABLED:
        return
    try:
        existing = db_client.list_users()
        if existing:
            logging.info("[Auth] DB already has users, skipping seed.")
            return
        logging.info("[Auth] DB is empty — seeding from users.json ...")
        users = _load_json_users()
        for username, data in users.items():
            try:
                db_client.create_user(
                    username=username,
                    password=data.get("password", ""),
                    role=data.get("role", "user"),
                    has_llm_access=data.get("has_llm_access", False),
                    access_requested=data.get("access_requested", False),
                )
                logging.info(f"[Auth] Seeded user: {username}")
            except Exception as e:
                logging.warning(f"[Auth] Seed failed for {username}: {e}")
    except DBServiceUnavailable:
        logging.warning("[Auth] DB service unavailable during seed — skipping.")
    except Exception as e:
        logging.error(f"[Auth] Seed error: {e}")


# Run seed when the app first handles a request (avoids issues at import time)
_seeded = False

@app.before_request
def ensure_seeded():
    global _seeded
    if not _seeded:
        _seed_db_from_json()
        _seeded = True


# ────────────────────────────────────────────────────────────
# JSON fallback helpers (used when DB_SERVICE_URL not set)
# ────────────────────────────────────────────────────────────

def _load_json_users():
    if not os.path.exists(USERS_FILE):
        default = {
            "admin": {"password": "admin123", "role": "admin", "has_llm_access": True},
            "debugger": {"password": "debugger123", "role": "debugger", "has_llm_access": False},
        }
        _save_json_users(default)
        return default
    try:
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
        if "debugger" not in users:
            users["debugger"] = {"password": "debugger123", "role": "debugger", "has_llm_access": False}
            _save_json_users(users)
        return users
    except Exception:
        return {}


def _save_json_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)


# ────────────────────────────────────────────────────────────
# Audit logging (stays local — not moved to DB)
# ────────────────────────────────────────────────────────────

def _load_audit():
    if not os.path.exists(AUDIT_FILE):
        return []
    try:
        with open(AUDIT_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_audit(logs):
    with open(AUDIT_FILE, "w") as f:
        json.dump(logs, f, indent=4)


def log_event(username, action, details=None):
    logs = _load_audit()
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "username": username,
        "action": action,
        "details": details or {},
    })
    _save_audit(logs)


# ────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "up", "service": "auth-service",
                    "db_enabled": DB_ENABLED}), 200


@app.route("/version")
def version():
    return jsonify({"version": APP_VERSION}), 200


# ── Signup ──────────────────────────────────────────────────

@app.route("/signup", methods=["POST"])
def signup():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Missing fields"}), 400

    if DB_ENABLED:
        try:
            existing = db_client.get_user(username)
            if existing:
                return jsonify({"error": "User already exists"}), 400
            db_client.create_user(username, password, role="user",
                                  has_llm_access=False, access_requested=False)
            log_event(username, "SIGNUP", {"status": "success"})
            return jsonify({"message": "User created"}), 201
        except DBServiceUnavailable:
            return jsonify({"error": "Database service unavailable"}), 503
        except Exception as e:
            logging.error(f"[Auth] signup error: {e}")
            return jsonify({"error": str(e)}), 500
    else:
        # JSON fallback
        users = _load_json_users()
        if username in users:
            return jsonify({"error": "User already exists"}), 400
        users[username] = {"password": password, "role": "user",
                           "has_llm_access": False, "access_requested": False}
        _save_json_users(users)
        log_event(username, "SIGNUP", {"status": "success"})
        return jsonify({"message": "User created"}), 201


# ── Login ────────────────────────────────────────────────────

@app.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    username = data.get("username", "")
    password = data.get("password", "")

    if DB_ENABLED:
        try:
            result = db_client.verify_password(username, password)
            if result.get("valid"):
                log_event(username, "LOGIN", {"status": "success"})
                return jsonify({
                    "message": "login success",
                    "role": result.get("role", "user"),
                    "has_llm_access": result.get("has_llm_access", False),
                }), 200
            log_event(username, "LOGIN", {"status": "failed_password"})
            return jsonify({"error": "invalid credentials"}), 401
        except DBServiceUnavailable:
            return jsonify({"error": "Database service unavailable"}), 503
        except Exception as e:
            logging.error(f"[Auth] login error: {e}")
            return jsonify({"error": str(e)}), 500
    else:
        users = _load_json_users()
        user = users.get(username)
        if user and user["password"] == password:
            log_event(username, "LOGIN", {"status": "success"})
            return jsonify({
                "message": "login success",
                "role": user["role"],
                "has_llm_access": user.get("has_llm_access", False),
            }), 200
        if user:
            log_event(username, "LOGIN", {"status": "failed_password"})
        return jsonify({"error": "invalid credentials"}), 401


# ── User List / Admin ────────────────────────────────────────

@app.route("/users", methods=["GET"])
def list_users():
    if DB_ENABLED:
        try:
            users = db_client.list_users()
            return jsonify({"users": users}), 200
        except DBServiceUnavailable:
            return jsonify({"error": "Database service unavailable"}), 503
    else:
        users = _load_json_users()
        result = [
            {
                "username": u,
                "role": d["role"],
                "has_llm_access": d.get("has_llm_access", False),
                "access_requested": d.get("access_requested", False),
            }
            for u, d in users.items()
        ]
        return jsonify({"users": result}), 200


@app.route("/users/pending", methods=["GET"])
def list_pending():
    if DB_ENABLED:
        try:
            pending = db_client.list_pending_users()
            return jsonify({"users": pending}), 200
        except DBServiceUnavailable:
            return jsonify({"error": "Database service unavailable"}), 503
    else:
        users = _load_json_users()
        pending = [u for u, d in users.items()
                   if d.get("access_requested") and not d.get("has_llm_access")]
        return jsonify({"users": pending}), 200


@app.route("/users/toggle-access", methods=["POST"])
def toggle_access():
    data = request.json or {}
    target_user = data.get("username")
    access = data.get("access")  # boolean

    if DB_ENABLED:
        try:
            user = db_client.get_user(target_user)
            if not user:
                return jsonify({"error": "User not found"}), 404
            update_fields = {"has_llm_access": access}
            if access:
                update_fields["access_requested"] = False
            db_client.update_user(target_user, update_fields)
            action = "ACCESS_GRANTED" if access else "ACCESS_REVOKED"
            log_event("admin", action, {"target_user": target_user})
            return jsonify({"status": "updated"}), 200
        except DBServiceUnavailable:
            return jsonify({"error": "Database service unavailable"}), 503
    else:
        users = _load_json_users()
        if target_user not in users:
            return jsonify({"error": "User not found"}), 404
        users[target_user]["has_llm_access"] = access
        if access:
            users[target_user]["access_requested"] = False
        _save_json_users(users)
        action = "ACCESS_GRANTED" if access else "ACCESS_REVOKED"
        log_event("admin", action, {"target_user": target_user})
        return jsonify({"status": "updated"}), 200


@app.route("/users/delete", methods=["POST"])
def delete_user():
    data = request.json or {}
    target_user = data.get("username")

    if DB_ENABLED:
        try:
            user = db_client.get_user(target_user)
            if not user:
                return jsonify({"error": "User not found"}), 404
            if user.get("role") == "admin":
                return jsonify({"error": "Cannot delete admin"}), 403
            if user.get("role") == "debugger":
                return jsonify({"error": "Cannot delete debugger"}), 403
            db_client.delete_user(target_user)
            log_event(target_user, "ACCOUNT_DELETED", {"by": "admin_or_self"})
            return jsonify({"status": "deleted"}), 200
        except DBServiceUnavailable:
            return jsonify({"error": "Database service unavailable"}), 503
    else:
        users = _load_json_users()
        if target_user not in users:
            return jsonify({"error": "User not found"}), 404
        if users[target_user]["role"] == "admin":
            return jsonify({"error": "Cannot delete admin"}), 403
        if users[target_user]["role"] == "debugger":
            return jsonify({"error": "Cannot delete debugger"}), 403
        del users[target_user]
        _save_json_users(users)
        log_event(target_user, "ACCOUNT_DELETED", {"by": "admin_or_self"})
        return jsonify({"status": "deleted"}), 200


# ── LLM Access Control ───────────────────────────────────────

@app.route("/access/request", methods=["POST"])
def request_access():
    username = (request.json or {}).get("username")

    if DB_ENABLED:
        try:
            user = db_client.get_user(username)
            if not user:
                return jsonify({"error": "user not found"}), 404
            db_client.update_user(username, {"access_requested": True})
            log_event(username, "REQUEST_ACCESS", {})
            return jsonify({"status": "requested"}), 200
        except DBServiceUnavailable:
            return jsonify({"error": "Database service unavailable"}), 503
    else:
        users = _load_json_users()
        if username not in users:
            return jsonify({"error": "user not found"}), 404
        users[username]["access_requested"] = True
        _save_json_users(users)
        log_event(username, "REQUEST_ACCESS", {})
        return jsonify({"status": "requested"}), 200


@app.route("/access/revoke", methods=["POST"])
def revoke_access():
    username = (request.json or {}).get("username")

    if DB_ENABLED:
        try:
            user = db_client.get_user(username)
            if not user:
                return jsonify({"error": "user not found"}), 404
            db_client.update_user(username, {"has_llm_access": False, "access_requested": False})
            log_event(username, "REMOVE_SERVICE", {})
            return jsonify({"status": "revoked"}), 200
        except DBServiceUnavailable:
            return jsonify({"error": "Database service unavailable"}), 503
    else:
        users = _load_json_users()
        if username not in users:
            return jsonify({"error": "user not found"}), 404
        users[username]["has_llm_access"] = False
        users[username]["access_requested"] = False
        _save_json_users(users)
        log_event(username, "REMOVE_SERVICE", {})
        return jsonify({"status": "revoked"}), 200


@app.route("/access/status", methods=["GET"])
def get_user_status():
    username = request.args.get("username")

    if DB_ENABLED:
        try:
            user = db_client.get_user(username)
            if not user:
                return jsonify({"status": "none"}), 200
            if user.get("has_llm_access"):
                return jsonify({"status": "approved"}), 200
            if user.get("access_requested"):
                return jsonify({"status": "pending"}), 200
            return jsonify({"status": "none"}), 200
        except DBServiceUnavailable:
            return jsonify({"error": "Database service unavailable"}), 503
    else:
        users = _load_json_users()
        user = users.get(username)
        if not user:
            return jsonify({"status": "none"}), 200
        if user.get("has_llm_access"):
            return jsonify({"status": "approved"}), 200
        if user.get("access_requested"):
            return jsonify({"status": "pending"}), 200
        return jsonify({"status": "none"}), 200


# ── Audit Logs ───────────────────────────────────────────────

@app.route("/audit/logs", methods=["GET"])
def get_audit_logs():
    logs = _load_audit()
    return jsonify({"logs": logs}), 200


# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
