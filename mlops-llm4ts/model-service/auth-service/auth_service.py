from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import logging
from datetime import datetime
from utils.logging import configure_logging

# --- CONFIGURATION ---
APP_VERSION = "1.0.0"
USERS_FILE = "users.json"
AUDIT_FILE = "audit.json"

app = Flask(__name__)
# Enable CORS for all routes (important for separate frontend)
CORS(app)
configure_logging(app)

# --- AUDIT LOGGING ---
def load_audit():
    if not os.path.exists(AUDIT_FILE):
        return []
    try:
        with open(AUDIT_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_audit(logs):
    with open(AUDIT_FILE, "w") as f:
        json.dump(logs, f, indent=4)

def log_event(username, action, details=None):
    logs = load_audit()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "username": username,
        "action": action,
        "details": details or {}
    }
    logs.append(entry)
    save_audit(logs)
#
# --- USER PERSISTENCE ---
def load_users():
    if not os.path.exists(USERS_FILE):
        # Default Admin & Debugger
        default_users = {
            "admin": {"password": "admin123", "role": "admin", "has_llm_access": True},
            "debugger": {"password": "debugger123", "role": "debugger", "has_llm_access": False}
        }
        save_users(default_users)
        return default_users
    
    # Ensure debugger exists if loaded from old file
    try:
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
            if "debugger" not in users:
                users["debugger"] = {"password": "debugger123", "role": "debugger", "has_llm_access": False}
                save_users(users)
            return users
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)


# --- ROUTES ---

@app.route("/health")
def health():
    return jsonify({"status": "up", "service": "auth-service"}), 200

@app.route("/version")
def version():
    return jsonify({"version": APP_VERSION}), 200

@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        return jsonify({"error": "Missing fields"}), 400
        
    users = load_users()
    if username in users:
        return jsonify({"error": "User already exists"}), 400
        
    # Create new user
    users[username] = {
        "password": password,
        "role": "user",
        "has_llm_access": False,
        "access_requested": False
    }
    save_users(users)
    
    log_event(username, "SIGNUP", {"status": "success"})
    return jsonify({"message": "User created"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    
    users = load_users()
    user = users.get(username)
    
    if user and user["password"] == password:
        log_event(username, "LOGIN", {"status": "success"})
        return jsonify({
            "message": "login success",
            "role": user["role"],
            "has_llm_access": user.get("has_llm_access", False)
        }), 200
    
    # Log failed attempt
    if user:
         log_event(username, "LOGIN", {"status": "failed_password"})
    
    return jsonify({"error": "invalid credentials"}), 401

# --- Admin Management Endpoints ---

@app.route("/users", methods=["GET"])
def list_users():
    users = load_users()
    user_list = []
    for u, data in users.items():
        user_list.append({
            "username": u,
            "role": data["role"],
            "has_llm_access": data.get("has_llm_access", False),
            "access_requested": data.get("access_requested", False)
        })
    return jsonify({"users": user_list}), 200

@app.route("/users/pending", methods=["GET"])
def list_pending():
    users = load_users()
    pending = []
    for u, data in users.items():
        if data.get("access_requested", False) and not data.get("has_llm_access", False):
            pending.append(u)
    return jsonify({"users": pending}), 200

@app.route("/users/toggle-access", methods=["POST"])
def toggle_access():
    data = request.json
    target_user = data.get("username")
    access = data.get("access") # boolean
    
    users = load_users()
    if target_user not in users:
        return jsonify({"error": "User not found"}), 404
        
    users[target_user]["has_llm_access"] = access
    if access:
        users[target_user]["access_requested"] = False
        
    save_users(users)
    
    action = "ACCESS_GRANTED" if access else "ACCESS_REVOKED"
    log_event("admin", action, {"target_user": target_user})
    
    return jsonify({"status": "updated"}), 200

@app.route("/users/delete", methods=["POST"])
def delete_user():
    data = request.json
    target_user = data.get("username")
    
    users = load_users()
    if target_user not in users:
        return jsonify({"error": "User not found"}), 404
    
    if users[target_user]["role"] == "admin":
        return jsonify({"error": "Cannot delete admin"}), 403
    if users[target_user]["role"] == "debugger":
        return jsonify({"error": "Cannot delete debugger"}), 403
        
    del users[target_user]
    save_users(users)
    
    log_event(target_user, "ACCOUNT_DELETED", {"by": "admin_or_self"})
    return jsonify({"status": "deleted"}), 200

@app.route("/access/request", methods=["POST"])
def request_access():
    username = request.json.get("username")
    users = load_users()
    
    if username in users:
        users[username]["access_requested"] = True
        save_users(users)
        log_event(username, "REQUEST_ACCESS", {})
        return jsonify({"status": "requested"}), 200
    return jsonify({"error": "user not found"}), 404

@app.route("/access/revoke", methods=["POST"])
def revoke_access():
    username = request.json.get("username")
    users = load_users()
    
    if username in users:
        users[username]["has_llm_access"] = False
        users[username]["access_requested"] = False
        save_users(users)
        log_event(username, "REMOVE_SERVICE", {})
        return jsonify({"status": "revoked"}), 200
    return jsonify({"error": "user not found"}), 404

@app.route("/access/status", methods=["GET"])
def get_user_status():
    username = request.args.get("username")
    users = load_users()
    user = users.get(username)
    
    if user:
         if user.get("has_llm_access"):
             return jsonify({"status": "approved"}), 200
         if user.get("access_requested"):
             return jsonify({"status": "pending"}), 200
         return jsonify({"status": "none"}), 200
    return jsonify({"status": "none"}), 200

@app.route("/audit/logs", methods=["GET"])
def get_audit_logs():
    logs = load_audit()
    return jsonify({"logs": logs}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
