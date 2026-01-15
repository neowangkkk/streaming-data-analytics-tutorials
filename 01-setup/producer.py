from confluent_kafka import Producer
import json
import socket
import time
from datetime import datetime, timezone


def delivery_report(err, msg):
    if err is not None:
        print(f"Delivery failed: {err}")
    else:
        print(f"Delivered: {msg.topic()} [{msg.partition()}] offset={msg.offset()}")


def main():
    producer = Producer(
        {
            "bootstrap.servers": "localhost:9092",
            "client.id": socket.gethostname(),
        }
    )

    topic = "demo"

    # Manually entered list
    people = [
        ("Alice", 29),
        ("Jack", 35),
        ("Max", 20),
    ]

    for i, (name, age) in enumerate(people, start=1):
        payload = {
            "event_id": i,
            "name": name,
            "age": age,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        producer.produce(
            topic,
            key=name,  # key helps keep the same person on the same partition
            value=json.dumps(payload),
            callback=delivery_report,
        )

        producer.poll(0)
        time.sleep(0.2)

    producer.flush(10)


if __name__ == "__main__":
    main()
