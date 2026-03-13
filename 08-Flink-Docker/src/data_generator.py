"""
data_generator.py -- Simulated Transaction Stream (Kafka Producer)
===================================================================
Generates a continuous stream of bank transactions and publishes them
to the Kafka topic "transactions" at a configurable rate.

Each message is a JSON-encoded transaction. The PyFlink fraud detector
reads from this topic via KafkaSource and applies fraud detection rules
in real time.

Message format:
{
    "transaction_id": "TXN-00001234",
    "customer_id":    "C0042",
    "amount":         249.99,
    "merchant":       "Grocery Store",
    "city":           "Toronto",
    "event_time":     1709650000000,    <- Unix ms (Flink event time)
    "hour":           14,
    "is_fraud_seed":  false
}

Usage:
    python src/data_generator.py
    python src/data_generator.py --rate 20 --fraud-ratio 0.05
"""

import json
import random
import time
import argparse
import os
from datetime import datetime, timezone
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC           = "transactions"

CUSTOMERS = [f"C{str(i).zfill(4)}" for i in range(1, 101)]
CITIES    = ["Toronto", "Vancouver", "Montreal", "Calgary", "Ottawa",
             "Edmonton", "Winnipeg", "Halifax", "Quebec City", "Victoria"]
MERCHANTS = ["Grocery Store", "Gas Station", "Restaurant", "Online Shop",
             "Electronics Store", "Pharmacy", "Hotel", "Airline", "ATM"]

NORMAL_AMOUNT_MEAN   = 150.0
NORMAL_AMOUNT_STDDEV = 200.0
MAX_NORMAL_AMOUNT    = 2000.0


# -----------------------------------------------------------------------------
# Transaction Factory
# -----------------------------------------------------------------------------

def make_transaction(customer_id: str,
                     amount: float,
                     city: str = None,
                     hour: int = None,
                     delay_ms: int = 0,
                     is_fraud_seed: bool = False) -> dict:
    """
    Build one transaction record.

    delay_ms: positive value sets event_time in the past, simulating
    out-of-order delivery. This exercises Flink's watermark handling.
    """
    now_ms        = int(time.time() * 1000)
    event_time_ms = now_ms - delay_ms

    if hour is None:
        hour = datetime.fromtimestamp(event_time_ms / 1000,
                                      tz=timezone.utc).hour
    return {
        "transaction_id": f"TXN-{random.randint(10_000_000, 99_999_999)}",
        "customer_id":    customer_id,
        "amount":         round(max(1.0, amount), 2),
        "merchant":       random.choice(MERCHANTS),
        "city":           city or random.choice(CITIES),
        "event_time":     event_time_ms,
        "hour":           hour,
        "is_fraud_seed":  is_fraud_seed,
    }


def normal_transaction() -> dict:
    """Generate a plausible normal transaction with slight out-of-orderness."""
    amount   = min(abs(random.gauss(NORMAL_AMOUNT_MEAN, NORMAL_AMOUNT_STDDEV)),
                   MAX_NORMAL_AMOUNT)
    delay_ms = random.randint(0, 2000)
    return make_transaction(random.choice(CUSTOMERS), amount, delay_ms=delay_ms)


# -----------------------------------------------------------------------------
# Fraud Scenario Generators
# -----------------------------------------------------------------------------

def fraud_rule1_high_value() -> list:
    """Rule R1: Single transaction exceeding $10,000."""
    return [make_transaction(random.choice(CUSTOMERS),
                             random.uniform(10_001, 50_000),
                             is_fraud_seed=True)]


def fraud_rule2_velocity() -> list:
    """
    Rule R2: More than 5 transactions within 60 seconds.
    Sends 8 rapid transactions for the same customer.
    """
    customer = random.choice(CUSTOMERS)
    return [
        make_transaction(customer,
                         random.uniform(10, 200),
                         delay_ms=random.randint(0, 500) + (i * 1200),
                         is_fraud_seed=True)
        for i in range(8)
    ]


def fraud_rule3_aggregate() -> list:
    """
    Rule R3: Total spend exceeding $50,000 in a 10-minute window.
    Sends 6 large transactions spread over ~5 minutes.
    """
    customer = random.choice(CUSTOMERS)
    return [
        make_transaction(customer,
                         random.uniform(8_000, 12_000),
                         delay_ms=random.randint(0, 30_000) + (i * 60_000),
                         is_fraud_seed=True)
        for i in range(6)
    ]


def fraud_rule4_night_owl() -> list:
    """Rule R4: Transaction between 01:00-04:00 with amount exceeding $3,000."""
    return [make_transaction(random.choice(CUSTOMERS),
                             random.uniform(3_001, 8_000),
                             hour=2,
                             is_fraud_seed=True)]


def fraud_rule5_escalation() -> list:
    """
    Rule R5: Each successive transaction more than 3x the previous.
    Escalation sequence: $10 -> ~$36 -> ~$130 -> ~$470 -> ~$1,700
    """
    customer = random.choice(CUSTOMERS)
    txns, amount = [], 10.0
    for _ in range(5):
        txns.append(make_transaction(customer, amount,
                                     delay_ms=random.randint(0, 1000),
                                     is_fraud_seed=True))
        amount *= random.uniform(3.2, 4.0)
    return txns


FRAUD_SCENARIOS = [
    fraud_rule1_high_value,
    fraud_rule2_velocity,
    fraud_rule3_aggregate,
    fraud_rule4_night_owl,
    fraud_rule5_escalation,
]


# -----------------------------------------------------------------------------
# Kafka Producer
# -----------------------------------------------------------------------------

def connect_producer(bootstrap: str, retries: int = 15) -> KafkaProducer:
    """
    Connect to Kafka with retries.
    Waits up to retries * 2 seconds for the broker to be available.
    """
    for attempt in range(1, retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=bootstrap,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                # Batch small messages for efficiency
                batch_size=16_384,
                linger_ms=10,
            )
            print(f"[Generator] Connected to Kafka at {bootstrap}")
            return producer
        except NoBrokersAvailable:
            print(f"[Generator] Kafka not ready, retrying "
                  f"({attempt}/{retries})...")
            time.sleep(2)
    raise RuntimeError(f"Could not connect to Kafka at {bootstrap} "
                       f"after {retries} attempts")


# -----------------------------------------------------------------------------
# Main Loop
# -----------------------------------------------------------------------------

def run(rate_per_second: float = 10.0, fraud_ratio: float = 0.03):
    """
    Publish transactions to Kafka continuously.

    Every (1/rate_per_second) seconds, publishes one normal transaction.
    Every (1/fraud_ratio) normal transactions, injects a fraud burst.

    Each transaction becomes one Kafka message on the "transactions" topic.
    Flink consumes these messages via KafkaSource as an unbounded stream.
    """
    producer      = connect_producer(KAFKA_BOOTSTRAP)
    fraud_counter = 0
    total_sent    = 0
    fraud_threshold = max(1, int(1.0 / fraud_ratio))
    sleep_interval  = 1.0 / rate_per_second

    print(f"[Generator] Publishing to topic '{TOPIC}' at {rate_per_second} txn/s")
    print(f"[Generator] Fraud injection: every ~{fraud_threshold} transactions")
    print("[Generator] Press Ctrl+C to stop\n")

    while True:
        try:
            # Normal transaction
            txn = normal_transaction()
            producer.send(TOPIC, value=txn)
            total_sent    += 1
            fraud_counter += 1

            # Inject fraud burst periodically
            if fraud_counter >= fraud_threshold:
                fraud_counter = 0
                scenario  = random.choice(FRAUD_SCENARIOS)
                fraud_txns = scenario()

                print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
                      f"Fraud burst: {scenario.__name__} "
                      f"({len(fraud_txns)} txn, "
                      f"customer={fraud_txns[0]['customer_id']})")

                for ft in fraud_txns:
                    producer.send(TOPIC, value=ft)
                    total_sent += 1

            if total_sent % 200 == 0:
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
                      f"Total published: {total_sent:,} transactions")

            time.sleep(sleep_interval)

        except KeyboardInterrupt:
            print(f"\n[Generator] Stopped. Total published: {total_sent:,}")
            producer.flush()
            producer.close()
            break


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kafka transaction generator")
    parser.add_argument("--rate",        type=float, default=10.0)
    parser.add_argument("--fraud-ratio", type=float, default=0.03)
    args = parser.parse_args()

    run(args.rate, args.fraud_ratio)
