from confluent_kafka import Consumer, KafkaException


def main():
    c = Consumer(
        {
            "bootstrap.servers": "localhost:9092",
            "group.id": "demo-group",
            "auto.offset.reset": "earliest",
        }
    )

    c.subscribe(["demo"])

    try:
        while True:
            msg = c.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())

            key = msg.key().decode("utf-8") if msg.key() else None
            val = msg.value().decode("utf-8") if msg.value() else None
            print(
                f"Consumed: topic={msg.topic()} partition={msg.partition()} offset={msg.offset()} key={key} value={val}"
            )

    except KeyboardInterrupt:
        pass
    finally:
        c.close()


if __name__ == "__main__":
    main()
