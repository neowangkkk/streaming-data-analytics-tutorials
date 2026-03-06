"""
data_generator.py — Simulated Transaction Stream
=================================================
Generates a continuous stream of bank transactions to a JSONL file.

The generator produces realistic normal traffic interspersed with
deliberate fraud scenarios to exercise each of the five detection rules.

Output format (one JSON object per line):
{
    "transaction_id": "TXN-00001234",
    "customer_id":    "C0042",
    "amount":         249.99,
    "merchant":       "Grocery Store",
    "city":           "Toronto",
    "event_time":     1709650000000,   ← Unix ms timestamp (event time)
    "hour":           14,
    "is_fraud_seed":  false             ← internal flag for simulation only
}

Usage:
    python data_generator.py
    python data_generator.py --rate 50 --fraud-ratio 0.05 --out transactions.jsonl
"""

import json
import random
import time
import argparse
import os
from datetime import datetime, timezone


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

CUSTOMERS = [f"C{str(i).zfill(4)}" for i in range(1, 101)]   # C0001 – C0100
CITIES    = ["Toronto", "Vancouver", "Montreal", "Calgary", "Ottawa",
             "Edmonton", "Winnipeg", "Halifax", "Quebec City", "Victoria"]
MERCHANTS = ["Grocery Store", "Gas Station", "Restaurant", "Online Shop",
             "Electronics Store", "Pharmacy", "Hotel", "Airline", "ATM"]

NORMAL_AMOUNT_MEAN   = 150.0    # Average normal transaction: $150
NORMAL_AMOUNT_STDDEV = 200.0    # With some variance
MAX_NORMAL_AMOUNT    = 2000.0


# ─────────────────────────────────────────────────────────────────────────────
# Transaction Factory
# ─────────────────────────────────────────────────────────────────────────────

def make_transaction(customer_id: str,
                     amount: float,
                     city: str = None,
                     hour: int = None,
                     delay_ms: int = 0,
                     is_fraud_seed: bool = False) -> dict:
    """
    Build a single transaction record.

    delay_ms: simulate out-of-order delivery.
        Positive → the event_time is set that many ms in the PAST
        (i.e., the event was created earlier but is arriving late).
        This exercises Flink's watermark / out-of-orderness handling.
    """
    now_ms = int(time.time() * 1000)
    event_time_ms = now_ms - delay_ms        # The time the transaction HAPPENED

    if hour is None:
        # Derive hour from event_time rather than current wall clock,
        # so delayed events still carry the correct event-time hour.
        hour = datetime.fromtimestamp(event_time_ms / 1000,
                                      tz=timezone.utc).hour

    return {
        "transaction_id": f"TXN-{random.randint(10_000_000, 99_999_999)}",
        "customer_id":    customer_id,
        "amount":         round(max(1.0, amount), 2),
        "merchant":       random.choice(MERCHANTS),
        "city":           city or random.choice(CITIES),
        "event_time":     event_time_ms,       # ← Flink uses this as event time
        "hour":           hour,
        "is_fraud_seed":  is_fraud_seed,
    }


def normal_transaction() -> dict:
    """Generate a plausible normal transaction."""
    amount = abs(random.gauss(NORMAL_AMOUNT_MEAN, NORMAL_AMOUNT_STDDEV))
    amount = min(amount, MAX_NORMAL_AMOUNT)
    # Slight out-of-orderness: up to 2 seconds late
    delay_ms = random.randint(0, 2000)
    return make_transaction(
        customer_id=random.choice(CUSTOMERS),
        amount=amount,
        delay_ms=delay_ms,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fraud Scenario Generators
# ─────────────────────────────────────────────────────────────────────────────
# Each function yields a burst of transactions that should trigger a
# specific fraud rule. This lets students verify their detection logic.

def fraud_rule1_high_value() -> list:
    """
    Rule R1: Single transaction > $10,000.
    Generates one transaction well above the threshold.
    """
    customer = random.choice(CUSTOMERS)
    amount = random.uniform(10_001, 50_000)
    return [make_transaction(customer, amount, is_fraud_seed=True)]


def fraud_rule2_velocity() -> list:
    """
    Rule R2: > 5 transactions within 60 seconds.
    Generates 8 rapid transactions for the same customer.
    All share the same approximate event_time (within ~10 seconds).

    Note: delay_ms is small and consistent so they all land
    in the same 60-second event-time window.
    """
    customer = random.choice(CUSTOMERS)
    txns = []
    for i in range(8):
        # Spread transactions over 10 seconds; small random latency
        delay_ms = random.randint(0, 500) + (i * 1200)
        txns.append(make_transaction(
            customer_id=customer,
            amount=random.uniform(10, 200),
            delay_ms=delay_ms,
            is_fraud_seed=True,
        ))
    return txns


def fraud_rule3_aggregate_amount() -> list:
    """
    Rule R3: Total spend > $50,000 in a 10-minute tumbling window.
    Generates 6 large-ish transactions that cumulatively exceed $50K.
    They are spread within a ~5-minute window.
    """
    customer = random.choice(CUSTOMERS)
    txns = []
    for i in range(6):
        # Spread over 5 minutes (300,000ms), 1 minute apart on average
        delay_ms = random.randint(0, 30_000) + (i * 60_000)
        txns.append(make_transaction(
            customer_id=customer,
            amount=random.uniform(8_000, 12_000),  # ~$9K each × 6 = ~$54K
            delay_ms=delay_ms,
            is_fraud_seed=True,
        ))
    return txns


def fraud_rule4_night_owl() -> list:
    """
    Rule R4: Transaction between 01:00–04:00 AND amount > $3,000.
    Explicitly sets the hour to 2 AM.
    """
    customer = random.choice(CUSTOMERS)
    return [make_transaction(
        customer_id=customer,
        amount=random.uniform(3_001, 8_000),
        hour=2,
        is_fraud_seed=True,
    )]


def fraud_rule5_escalation() -> list:
    """
    Rule R5: Each successive transaction is > 3× the previous amount.
    Starts at $10, then $40, $160, $640 — a classic synthetic escalation.
    """
    customer = random.choice(CUSTOMERS)
    txns = []
    amount = 10.0
    for _ in range(5):
        txns.append(make_transaction(
            customer_id=customer,
            amount=amount,
            delay_ms=random.randint(0, 1000),
            is_fraud_seed=True,
        ))
        amount *= random.uniform(3.2, 4.0)   # escalate by 3–4×
    return txns


# ─────────────────────────────────────────────────────────────────────────────
# Main Loop
# ─────────────────────────────────────────────────────────────────────────────

FRAUD_SCENARIOS = [
    fraud_rule1_high_value,
    fraud_rule2_velocity,
    fraud_rule3_aggregate_amount,
    fraud_rule4_night_owl,
    fraud_rule5_escalation,
]


def run(output_file: str,
        rate_per_second: float = 10.0,
        fraud_ratio: float = 0.03):
    """
    Main generator loop.

    Continuously appends transactions to `output_file` at approximately
    `rate_per_second` transactions per second. Every `1/fraud_ratio`
    normal transactions, inject a random fraud scenario.

    The PyFlink job tails this file as a streaming source.
    """
    sleep_interval = 1.0 / rate_per_second
    fraud_counter = 0
    total_written = 0
    fraud_threshold = int(1 / fraud_ratio)

    print(f"[Generator] Writing to: {output_file}")
    print(f"[Generator] Rate: {rate_per_second} txn/s  |  "
          f"Fraud injection: every ~{fraud_threshold} normal transactions")
    print("[Generator] Press Ctrl+C to stop\n")

    # Open in append mode so PyFlink can tail the file live
    with open(output_file, "a", buffering=1) as f:   # line-buffered
        while True:
            try:
                # ── Normal transaction ─────────────────────────────────────
                txn = normal_transaction()
                f.write(json.dumps(txn) + "\n")
                total_written += 1
                fraud_counter += 1

                # ── Inject fraud scenario periodically ────────────────────
                if fraud_counter >= fraud_threshold:
                    fraud_counter = 0
                    scenario = random.choice(FRAUD_SCENARIOS)
                    fraud_txns = scenario()
                    scenario_name = scenario.__name__

                    print(f"  💥 Injecting fraud scenario: {scenario_name} "
                          f"({len(fraud_txns)} txn, customer={fraud_txns[0]['customer_id']})")

                    for ft in fraud_txns:
                        f.write(json.dumps(ft) + "\n")
                        total_written += 1

                if total_written % 100 == 0:
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(f"  [{ts}] Total transactions written: {total_written}")

                time.sleep(sleep_interval)

            except KeyboardInterrupt:
                print(f"\n[Generator] Stopped. Total written: {total_written}")
                break


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transaction stream generator")
    parser.add_argument("--out",          default="data/transactions.jsonl",
                        help="Output JSONL file path")
    parser.add_argument("--rate",         type=float, default=10.0,
                        help="Target transactions per second (default: 10)")
    parser.add_argument("--fraud-ratio",  type=float, default=0.03,
                        help="Approximate fraction of events in fraud bursts (default: 0.03)")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out) if os.path.dirname(args.out) else ".", exist_ok=True)
    run(args.out, args.rate, args.fraud_ratio)
