"""
db_client.py — Thin HTTP client for the DB microservice.

Used by auth-service and inference-service to talk to db-service.
Falls back gracefully (raises DBServiceUnavailable) when DB_SERVICE_URL is not set
or the service is unreachable — callers decide how to handle the fallback.
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

DB_SERVICE_URL = os.getenv("DB_SERVICE_URL", "").rstrip("/")
TIMEOUT = 5  # seconds


class DBServiceUnavailable(Exception):
    """Raised when DB_SERVICE_URL is not configured or the service is unreachable."""
    pass


def _is_configured():
    return bool(DB_SERVICE_URL)


def _url(path: str) -> str:
    return f"{DB_SERVICE_URL}{path}"


# ──────────────────────────────────────────────────────────────
# User operations
# ──────────────────────────────────────────────────────────────

def create_user(username: str, password: str, role: str = "user",
                has_llm_access: bool = False, access_requested: bool = False) -> dict:
    if not _is_configured():
        raise DBServiceUnavailable("DB_SERVICE_URL not set")
    resp = requests.post(_url("/users"), json={
        "username": username,
        "password": password,
        "role": role,
        "has_llm_access": has_llm_access,
        "access_requested": access_requested,
    }, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


from typing import Optional, List, Union

def get_user(username: str) -> Optional[dict]:
    """Returns user dict or None if not found."""
    if not _is_configured():
        raise DBServiceUnavailable("DB_SERVICE_URL not set")
    resp = requests.get(_url(f"/users/{username}"), timeout=TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def list_users() -> list:
    if not _is_configured():
        raise DBServiceUnavailable("DB_SERVICE_URL not set")
    resp = requests.get(_url("/users"), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("users", [])


def list_pending_users() -> list:
    if not _is_configured():
        raise DBServiceUnavailable("DB_SERVICE_URL not set")
    resp = requests.get(_url("/users/pending"), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("users", [])


def update_user(username: str, fields: dict) -> dict:
    if not _is_configured():
        raise DBServiceUnavailable("DB_SERVICE_URL not set")
    resp = requests.put(_url(f"/users/{username}"), json=fields, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def delete_user(username: str) -> dict:
    if not _is_configured():
        raise DBServiceUnavailable("DB_SERVICE_URL not set")
    resp = requests.delete(_url(f"/users/{username}"), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def verify_password(username: str, password: str) -> dict:
    """Returns { valid: bool, role, has_llm_access, access_requested } or raises."""
    if not _is_configured():
        raise DBServiceUnavailable("DB_SERVICE_URL not set")
    resp = requests.post(_url(f"/users/{username}/verify"),
                         json={"password": password}, timeout=TIMEOUT)
    if resp.status_code in (401, 404):
        return {"valid": False}
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────────────────────
# Inference log operations
# ──────────────────────────────────────────────────────────────

def log_inference(user_id: str, model_name: str, lat: float, lon: float):
    """Best-effort log — does not raise on failure (non-blocking)."""
    if not _is_configured():
        return
    try:
        requests.post(_url("/inference-log"), json={
            "user_id": user_id,
            "model_name": model_name,
            "lat": lat,
            "lon": lon,
        }, timeout=TIMEOUT)
    except Exception as e:
        logger.warning(f"[DB Client] inference log failed (non-fatal): {e}")


def get_inference_history(user_id: str) -> list:
    if not _is_configured():
        raise DBServiceUnavailable("DB_SERVICE_URL not set")
    resp = requests.get(_url(f"/inference-log/{user_id}"), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("history", [])
