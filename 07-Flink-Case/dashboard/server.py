"""
dashboard/server.py — Real-Time Fraud Detection Dashboard Server
================================================================
A lightweight Flask server that:
  1. Tails alerts.jsonl (written by the PyFlink job) every 2 seconds
  2. Serves the current alert data as JSON via a REST API
  3. Serves the dashboard HTML page

Endpoints:
  GET /               → dashboard HTML page
  GET /api/alerts     → last N alerts as JSON
  GET /api/stats      → aggregated statistics for charts

Run:
    python dashboard/server.py
Then open: http://localhost:8050
"""

import json
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock

from flask import Flask, jsonify, render_template_string, send_from_directory

# ─────────────────────────────────────────────────────────────────────────────
# In-memory alert store (thread-safe ring buffer)
# ─────────────────────────────────────────────────────────────────────────────

MAX_ALERTS_IN_MEMORY = 500
alert_store: deque = deque(maxlen=MAX_ALERTS_IN_MEMORY)
store_lock = Lock()

# ─────────────────────────────────────────────────────────────────────────────
# Alert file reader (tails the JSONL file written by PyFlink)
# ─────────────────────────────────────────────────────────────────────────────

ALERT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "alerts.jsonl"
)


def tail_alerts():
    """
    Background loop: reads new lines from alerts.jsonl as they are appended
    by the PyFlink job and pushes them into alert_store.

    This mimics a simplified Kafka consumer: the PyFlink job is the producer,
    and this function is the consumer.

    In production: replace with a real Kafka consumer (confluent-kafka-python)
    subscribing to the "fraud-alerts" topic.
    """
    print(f"[Dashboard] Tailing alert file: {ALERT_FILE}")
    last_size = 0

    while True:
        try:
            if os.path.exists(ALERT_FILE):
                current_size = os.path.getsize(ALERT_FILE)
                if current_size > last_size:
                    with open(ALERT_FILE, "r") as f:
                        f.seek(last_size)
                        new_lines = f.read()
                    last_size = current_size

                    for line in new_lines.strip().split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            alert = json.loads(line)
                            with store_lock:
                                alert_store.append(alert)
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            print(f"[Dashboard] Error reading alerts: {e}")

        time.sleep(2.0)   # Poll every 2 seconds


# ─────────────────────────────────────────────────────────────────────────────
# Statistics aggregation
# ─────────────────────────────────────────────────────────────────────────────

def compute_stats() -> dict:
    """
    Compute aggregated statistics for the dashboard charts.
    Called on every /api/stats request.
    """
    with store_lock:
        alerts = list(alert_store)

    if not alerts:
        return {
            "total_alerts":     0,
            "alerts_by_rule":   {},
            "alerts_over_time": [],
            "top_customers":    [],
            "avg_risk_score":   0,
            "high_risk_count":  0,
        }

    # ── Alerts by rule ──────────────────────────────────────────────────────
    rule_counts = defaultdict(int)
    for a in alerts:
        rule_counts[a.get("rule_id", "?")] += 1

    # ── Alerts over time (1-minute buckets, last 30 minutes) ───────────────
    now_ms  = int(time.time() * 1000)
    buckets = {}
    for a in alerts:
        ts     = a.get("alert_time", a.get("event_time", now_ms))
        bucket = (ts // 60_000) * 60_000     # round down to nearest minute
        buckets[bucket] = buckets.get(bucket, 0) + 1

    # Fill in empty buckets for the last 30 minutes
    alerts_over_time = []
    for i in range(30, 0, -1):
        bucket_key = ((now_ms - i * 60_000) // 60_000) * 60_000
        dt = datetime.fromtimestamp(bucket_key / 1000,
                                    tz=timezone.utc).strftime("%H:%M")
        alerts_over_time.append({
            "time":  dt,
            "count": buckets.get(bucket_key, 0)
        })

    # ── Top risky customers ─────────────────────────────────────────────────
    customer_risk = defaultdict(list)
    for a in alerts:
        customer_risk[a["customer_id"]].append(a.get("risk_score", 0))

    top_customers = sorted(
        [
            {
                "customer_id": cid,
                "alert_count": len(scores),
                "max_risk":    round(max(scores), 1),
                "avg_risk":    round(sum(scores) / len(scores), 1),
            }
            for cid, scores in customer_risk.items()
        ],
        key=lambda x: x["max_risk"],
        reverse=True,
    )[:10]

    # ── Risk score distribution ─────────────────────────────────────────────
    risk_scores = [a.get("risk_score", 0) for a in alerts]
    avg_risk    = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0
    high_risk   = sum(1 for s in risk_scores if s >= 80)

    return {
        "total_alerts":     len(alerts),
        "alerts_by_rule":   dict(rule_counts),
        "alerts_over_time": alerts_over_time,
        "top_customers":    top_customers,
        "avg_risk_score":   avg_risk,
        "high_risk_count":  high_risk,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Flask app
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)


@app.route("/")
def index():
    """Serve the dashboard HTML (from same directory)."""
    dashboard_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(dashboard_path, "r") as f:
        return f.read()


@app.route("/api/alerts")
def get_alerts():
    """Return last 50 alerts, newest first."""
    with store_lock:
        recent = list(alert_store)[-50:][::-1]
    return jsonify(recent)


@app.route("/api/stats")
def get_stats():
    """Return aggregated dashboard statistics."""
    return jsonify(compute_stats())


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import threading

    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "data"),
                exist_ok=True)

    # Start the alert file tailer in a background thread
    tailer = threading.Thread(target=tail_alerts, daemon=True)
    tailer.start()

    print("=" * 50)
    print("  Fraud Detection Dashboard")
    print("  http://localhost:8050")
    print("=" * 50)

    app.run(host="0.0.0.0", port=8050, debug=False)
