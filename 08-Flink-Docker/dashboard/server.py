"""
dashboard/server.py -- Real-Time Fraud Detection Dashboard
==========================================================
Consumes fraud alerts from the Kafka "fraud-alerts" topic and serves a
live dashboard over HTTP.

Unlike the previous version (which polled a JSONL file), this server
is a real Kafka consumer. Alerts arrive within milliseconds of being
produced by the Flink job -- no file I/O, no polling delay.

Endpoints
---------
GET /              Dashboard HTML page
GET /api/alerts    Last 50 alerts (newest first) as JSON
GET /api/stats     Aggregated stats for charts as JSON

Architecture
------------
  KafkaConsumer thread  <-- "fraud-alerts" topic
       |
       v
  alert_store (thread-safe deque, max 500 alerts)
       |
       v
  Flask API  -->  browser (polls /api/stats every 2s via JavaScript)

Run:
    python dashboard/server.py
    http://localhost:8050
"""

import json
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock, Thread

from flask import Flask, jsonify
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
ALERTS_TOPIC    = os.getenv("ALERTS_TOPIC",    "fraud-alerts")
PORT            = int(os.getenv("PORT", 8050))

MAX_ALERTS = 500


# -----------------------------------------------------------------------------
# Thread-safe alert store
# -----------------------------------------------------------------------------

alert_store: deque = deque(maxlen=MAX_ALERTS)
store_lock = Lock()


# -----------------------------------------------------------------------------
# Kafka consumer thread
# -----------------------------------------------------------------------------

def consume_alerts():
    """
    Background thread: consumes messages from the fraud-alerts Kafka topic
    and pushes each alert into the in-memory store.

    This is a real Kafka consumer. It reconnects automatically if the broker
    is temporarily unavailable at startup.
    """
    consumer = None
    while consumer is None:
        try:
            consumer = KafkaConsumer(
                ALERTS_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                group_id="dashboard-consumer",
                # Read all alerts since the start of the topic so the
                # dashboard shows history from the current session.
                auto_offset_reset="earliest",
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                # Short session timeout for quick reconnection
                session_timeout_ms=10_000,
                heartbeat_interval_ms=3_000,
            )
            print(f"[Dashboard] Connected to Kafka, consuming '{ALERTS_TOPIC}'")
        except NoBrokersAvailable:
            print("[Dashboard] Kafka not ready, retrying in 3s...")
            time.sleep(3)

    for message in consumer:
        try:
            alert = message.value
            with store_lock:
                alert_store.append(alert)
        except Exception as e:
            print(f"[Dashboard] Error processing message: {e}")


# -----------------------------------------------------------------------------
# Statistics aggregation
# -----------------------------------------------------------------------------

def compute_stats() -> dict:
    """
    Compute aggregated statistics for the dashboard charts.
    Called on every /api/stats request (every 2 seconds from the browser).
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

    # -- Alerts by rule -------------------------------------------------------
    rule_counts = defaultdict(int)
    for a in alerts:
        rule_counts[a.get("rule_id", "?")] += 1

    # -- Alerts over time (1-minute buckets by alert_time) --------------------
    # We bucket by alert_time (when Flink emitted the alert) because this
    # reflects the real-time detection rate -- when did the system find fraud?
    # In a live stream, alert_time closely tracks event_time.
    now_ms  = int(time.time() * 1000)
    buckets = {}
    for a in alerts:
        ts     = a.get("alert_time", now_ms)
        bucket = (ts // 60_000) * 60_000
        buckets[bucket] = buckets.get(bucket, 0) + 1

    alerts_over_time = []
    for i in range(30, 0, -1):
        bkey = ((now_ms - i * 60_000) // 60_000) * 60_000
        dt   = datetime.fromtimestamp(bkey / 1000,
                                      tz=timezone.utc).strftime("%H:%M")
        alerts_over_time.append({"time": dt, "count": buckets.get(bkey, 0)})

    # -- Top risky customers --------------------------------------------------
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

    # -- Risk score summary ---------------------------------------------------
    risk_scores = [a.get("risk_score", 0) for a in alerts]
    avg_risk    = round(sum(risk_scores) / len(risk_scores), 1)
    high_risk   = sum(1 for s in risk_scores if s >= 80)

    return {
        "total_alerts":     len(alerts),
        "alerts_by_rule":   dict(rule_counts),
        "alerts_over_time": alerts_over_time,
        "top_customers":    top_customers,
        "avg_risk_score":   avg_risk,
        "high_risk_count":  high_risk,
    }


# -----------------------------------------------------------------------------
# Flask app
# -----------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/")
def index():
    dashboard_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(dashboard_path) as f:
        return f.read()


@app.route("/api/alerts")
def get_alerts():
    """Return the last 50 alerts, newest first."""
    with store_lock:
        recent = list(alert_store)[-50:][::-1]
    return jsonify(recent)


@app.route("/api/stats")
def get_stats():
    """Return aggregated stats for all dashboard charts."""
    return jsonify(compute_stats())


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "data"),
                exist_ok=True)

    # Start Kafka consumer in background thread
    Thread(target=consume_alerts, daemon=True).start()

    print("=" * 50)
    print("  Fraud Detection Dashboard")
    print(f"  http://localhost:{PORT}")
    print("=" * 50)

    app.run(host="0.0.0.0", port=PORT, debug=False)
