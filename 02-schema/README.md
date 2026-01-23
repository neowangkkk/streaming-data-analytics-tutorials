
# Week 3 Tutorial: Kafka + JSON Schema

This tutorial extends the Week 2 Kafka pipeline by adding **JSON Schema** using
Confluent Schema Registry.

## Files
- docker-compose.yml – Kafka (KRaft), Schema Registry, Kafka UI
- requirements.txt
- producer.py – JSON Schema–aware producer
- consumer.py – JSON Schema–aware consumer
- schemas/person_event.schema.json – message schema

## Steps
1. Start Kafka and Schema Registry:
   docker compose up -d

2. Install Python dependency:
   pip install confluent-kafka

3. Run consumer (Terminal 1):
   python consumer.py

4. Run producer (Terminal 2):
   python producer.py

## Learning goal
Producers register schemas, messages carry schema IDs,
and consumers safely deserialize data using the same schema.
