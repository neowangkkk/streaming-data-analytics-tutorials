import json
import socket
from confluent_kafka import Consumer, Producer, KafkaError
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.json_schema import JSONDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField

IN_TOPIC = "payments.raw"
OUT_APPROVED = "payments.approved"
OUT_FLAGGED = "payments.flagged"
DLQ = "payments.dlq"

RISKY_COUNTRIES = {"NG", "RU"}
HIGH_RISK_CATEGORIES = {"GIFT_CARDS", "CRYPTO"}
HIGH_AMOUNT = 400.0

def score_event(e: dict) -> tuple[int, list[str]]:
    # Stateless rule-based scoring: each event is judged independently
    score = 0
    reasons = []

    if e["amount"] >= HIGH_AMOUNT:
        score += 40
        reasons.append("high_amount")

    if e["country"] in RISKY_COUNTRIES:
        score += 30
        reasons.append("risky_country")

    if e["merchant_category"] in HIGH_RISK_CATEGORIES:
        score += 30
        reasons.append("high_risk_category")

    if e["ip_country"] != e["country"]:
        score += 25
        reasons.append("ip_country_mismatch")

    if e["channel"] == "ATM" and e["amount"] >= 200:
        score += 20
        reasons.append("large_atm_withdrawal")

    return score, reasons

def msg_headers_to_dict(msg) -> dict[str, bytes]:
    h = msg.headers() or []
    out = {}
    for k, v in h:
        if k is not None and v is not None:
            out[k] = v
    return out

def main():
    schema_str = open("schema_payment.json", "r", encoding="utf-8").read()
    sr = SchemaRegistryClient({"url": "http://localhost:8081"})

    def from_dict(d, ctx):
        return d

    deserializer = JSONDeserializer(schema_str, sr, from_dict)

    consumer = Consumer({
        "bootstrap.servers": "localhost:9092",
        "group.id": "fraud-detector",
        "client.id": f"fraud-detector-{socket.gethostname()}",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False
    })

    producer = Producer({
        "bootstrap.servers": "localhost:9092",
        "client.id": f"fraud-detector-producer-{socket.gethostname()}",
        "acks": 1
    })

    consumer.subscribe([IN_TOPIC])
    print("Stateless fraud detector started. Ctrl+C to stop.")

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"Consumer error: {msg.error()}")
                continue

            incoming_headers = msg_headers_to_dict(msg)

            # 1) Deserialize (schema-aware)
            try:
                event = deserializer(msg.value(), SerializationContext(IN_TOPIC, MessageField.VALUE))
            except Exception as e:
                dlq_payload = {
                    "error": str(e),
                    "topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                    "key": (msg.key() or b"").decode("utf-8", errors="replace"),
                    "excel_row": incoming_headers.get("excel_row", b"").decode("utf-8", errors="replace")
                }
                producer.produce(
                    DLQ,
                    value=json.dumps(dlq_payload).encode("utf-8"),
                    headers=list(incoming_headers.items())
                )
                producer.flush()
                consumer.commit(message=msg, asynchronous=False)
                continue

            # 2) Stateless filter: ignore zero-amount (simple demo rule)
            if event["amount"] == 0:
                consumer.commit(message=msg, asynchronous=False)
                continue

            # 3) Stateless map: compute risk score and annotate
            score, reasons = score_event(event)
            event["risk_score"] = score
            event["risk_reasons"] = reasons

            # 4) Stateless branch: route
            out_topic = OUT_FLAGGED if score >= 60 else OUT_APPROVED

            # 5) Propagate tracing headers (excel_row) + add processing metadata
            out_headers = list(incoming_headers.items()) + [
                ("processed_by", consumer._config["client.id"].encode("utf-8")),
                ("model", b"rules_v1"),
                ("routed_to", out_topic.encode("utf-8")),
            ]

            producer.produce(
                out_topic,
                key=msg.key(),
                value=json.dumps(event).encode("utf-8"),
                headers=out_headers,
            )
            producer.flush()

            # Commit only after successful produce (simple at-least-once pattern)
            consumer.commit(message=msg, asynchronous=False)

    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()

if __name__ == "__main__":
    main()
