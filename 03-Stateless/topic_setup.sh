#!/usr/bin/env bash
set -euo pipefail

docker exec -it broker kafka-topics --bootstrap-server broker:9092 --create --topic payments.raw --partitions 3 --replication-factor 1 || true
docker exec -it broker kafka-topics --bootstrap-server broker:9092 --create --topic payments.approved --partitions 3 --replication-factor 1 || true
docker exec -it broker kafka-topics --bootstrap-server broker:9092 --create --topic payments.flagged --partitions 3 --replication-factor 1 || true
docker exec -it broker kafka-topics --bootstrap-server broker:9092 --create --topic payments.dlq --partitions 3 --replication-factor 1 || true

echo "Topics are ready."
