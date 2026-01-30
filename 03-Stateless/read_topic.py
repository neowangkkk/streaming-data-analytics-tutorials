import sys
from confluent_kafka import Consumer

topic = sys.argv[1]

c = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": f"reader-{topic}",
    "auto.offset.reset": "earliest",
})
c.subscribe([topic])

print(f"Reading {topic}. Ctrl+C to stop.")
try:
    while True:
        msg = c.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            print(msg.error())
            continue
        print(msg.value().decode("utf-8", errors="replace"))
except KeyboardInterrupt:
    pass
finally:
    c.close()
