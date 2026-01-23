import socket
import time
from datetime import datetime, timezone
from pathlib import Path

from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.json_schema import JSONSerializer
from confluent_kafka.serialization import StringSerializer, SerializationContext, MessageField
from confluent_kafka import SerializingProducer


def delivery_report(err, msg):
    if err is not None:
        print(f"Delivery failed: {err}")
    else:
        print(f"Delivered: {msg.topic()} [{msg.partition()}] offset={msg.offset()}")


def main():
    topic = "demo"

    # 1) Schema Registry client
    schema_registry_conf = {"url": "http://localhost:8081"}
    schema_registry_client = SchemaRegistryClient(schema_registry_conf)

    # 2) Load JSON Schema (string)
    schema_str = Path("schemas/person_event.schema.json").read_text()

    # 3) Serializer (dict -> bytes + schema id)
    def to_dict(obj, ctx):
        return obj

    json_serializer = JSONSerializer(schema_str, schema_registry_client, to_dict)

    producer_conf = {
        "bootstrap.servers": "localhost:9092",
        "client.id": socket.gethostname(),
        "key.serializer": StringSerializer("utf_8"),
        "value.serializer": json_serializer,
    }
    producer = SerializingProducer(producer_conf)

    people = [("Tom", 29), ("Mary", 35), ("Nico", 20)]

    for i, (name, age) in enumerate(people, start=1):
        payload = {
            "event_id": i,
            "name": name,
            "age": age,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        producer.produce(
            topic=topic,
            key=name,
            value=payload,
            on_delivery=delivery_report,
        )
        producer.poll(0)
        time.sleep(0.2)

    producer.flush(10)


if __name__ == "__main__":
    main()
