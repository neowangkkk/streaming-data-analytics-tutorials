from pathlib import Path

from confluent_kafka import DeserializingConsumer, KafkaException
from confluent_kafka.serialization import StringDeserializer, SerializationContext
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.json_schema import JSONDeserializer


def main():
    print("Consumer started, waiting for messages... (Ctrl+C to stop)")

    schema_str = Path("schemas/person_event.schema.json").read_text()
    schema_registry_client = SchemaRegistryClient({"url": "http://localhost:8081"})

    # Must be: from_dict(dict, SerializationContext) -> object
    def from_dict(obj: dict, ctx: SerializationContext):
        return obj

    # ✅ Correct argument order: (schema_str, from_dict, schema_registry_client)
    json_deserializer = JSONDeserializer(
        schema_str,
        from_dict=from_dict,
        schema_registry_client=schema_registry_client,
    )

    consumer = DeserializingConsumer(
        {
            "bootstrap.servers": "localhost:9092",
            "group.id": "demo-group-debug-5",  # fresh group so you see messages
            "auto.offset.reset": "earliest",
            "key.deserializer": StringDeserializer("utf_8"),
            "value.deserializer": json_deserializer,
        }
    )

    consumer.subscribe(["demo"])
    print("Subscribed to topic: demo")

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())

            print(
                f"Consumed: topic={msg.topic()} partition={msg.partition()} "
                f"offset={msg.offset()} key={msg.key()} value={msg.value()}"
            )

    except KeyboardInterrupt:
        print("\nStopping consumer...")
    finally:
        consumer.close()
        print("Consumer closed.")


if __name__ == "__main__":
    main()
