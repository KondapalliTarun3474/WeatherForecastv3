import requests as http_requests
import pandas as pd
import numpy as np
from io import StringIO
from datetime import datetime, timedelta
import torch
import os
import sys
import logging

# Add parent path so db_client can be shared — or use a local copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model_loader import load_model


T_IN = 60       # Look-back window
T_OUT = 10      # Forecast horizon

DB_SERVICE_URL = os.getenv("DB_SERVICE_URL", "").rstrip("/")
DB_TIMEOUT = 5


def _log_to_db(user_id: str, model_name: str, lat: float, lon: float):
    """Best-effort fire-and-forget: log inference to db-service."""
    if not DB_SERVICE_URL or not user_id:
        return
    try:
        http_requests.post(
            f"{DB_SERVICE_URL}/inference-log",
            json={"user_id": user_id, "model_name": model_name, "lat": lat, "lon": lon},
            timeout=DB_TIMEOUT,
        )
    except Exception as e:
        logging.warning(f"[Forecast] DB log failed (non-fatal): {e}")


def fetch_nasa_data(lat, lon, param="T2M"):
    """Fetch last 5 years of weather data from NASA POWER API."""
    now = datetime.now()
    start = now - timedelta(days=(5 * 365 + 4))

    url = (
        "https://power.larc.nasa.gov/api/temporal/daily/point?"
        f"parameters={param}&community=AG&longitude={lon}&latitude={lat}"
        f"&start={start.strftime('%Y%m%d')}&end={now.strftime('%Y%m%d')}&format=CSV"
    )

    response = http_requests.get(url)
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text), skiprows=9)
    df.columns = [c.strip() for c in df.columns]

    df["Date"] = pd.to_datetime(
        df["YEAR"].astype(str) + df["DOY"].astype(str).str.zfill(3),
        format="%Y%j"
    )
    df.set_index("Date", inplace=True)

    return df[param].values.astype(np.float32)


def preprocess_series(series):
    """Normalize and return sliding window arrays."""
    mean = series.mean()
    std = series.std() if series.std() > 0 else 1.0

    normalized = (series - mean) / std

    # build sliding window for prediction
    last_window = normalized[-T_IN:]

    last_window_tensor = torch.tensor(
        last_window, dtype=torch.float32
    ).unsqueeze(0).unsqueeze(-1)

    temporal_info = torch.arange(T_IN, dtype=torch.float32).unsqueeze(0)

    return last_window_tensor, temporal_info, mean, std


def postprocess(pred_norm, mean, std):
    """Convert normalized predictions back to real values."""
    pred = pred_norm * std + mean

    dates = [
        (datetime.now() + timedelta(days=i+1)).strftime("%Y-%m-%d")
        for i in range(T_OUT)
    ]

    return [
        {"date": dates[i], "value": float(pred[i])}
        for i in range(T_OUT)
    ]


def run_forecast(lat, lon, param="T2M", user_id: str = None):
    """
    Main function called by param_service.py
    Fetch → preprocess → run model → postprocess → log to DB → return JSON
    """
    # 1. Fetch NASA POWER data
    series = fetch_nasa_data(lat, lon, param)

    if len(series) < T_IN:
        raise ValueError("Not enough data retrieved from NASA API")

    # 2. Preprocess (sliding windows + normalization)
    window_tensor, temporal_info, mean, std = preprocess_series(series)

    # 3. Load Model
    model = load_model(param)

    # 4. Inference
    with torch.no_grad():
        pred_norm = model(window_tensor, temporal_info).cpu().numpy().flatten()

    # 5. Log to DB (best-effort, non-blocking)
    _log_to_db(user_id=user_id, model_name=param, lat=lat, lon=lon)

    # 6. Denormalize + return response
    return postprocess(pred_norm, mean, std)
