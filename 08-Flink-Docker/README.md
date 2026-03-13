# Real-Time Fraud Detection with Apache Kafka and PyFlink

A complete streaming data pipeline that detects fraudulent bank transactions
in real time using Apache Kafka as the message broker and Apache Flink as
the stream processing engine.

---

## Architecture

```
data_generator  -->  Kafka ("transactions")  -->  PyFlink job
                                                       |
                                                       v
dashboard  <--  Kafka ("fraud-alerts")  <--  Flink KafkaSink
```

Each component runs in its own Docker container. All communication between
components happens through Kafka topics -- no shared files, no polling.

| Component      | Role                                               | Image                  |
|----------------|----------------------------------------------------|------------------------|
| kafka          | Message broker (KRaft mode, no Zookeeper)          | apache/kafka:3.7.0     |
| jobmanager     | Flink cluster coordinator                          | Dockerfile.flink       |
| taskmanager    | Flink operator executor                            | Dockerfile.flink       |
| detector       | Submits PyFlink fraud detection job to cluster     | Dockerfile.flink       |
| generator      | Publishes simulated transactions to Kafka          | Dockerfile.generator   |
| dashboard      | Consumes fraud alerts from Kafka, serves web UI    | Dockerfile.dashboard   |

---

## Kafka vs Flink -- What Each Does

A common question is: why do we need both?

Kafka is a distributed log. It receives messages, stores them durably, and
lets multiple consumers read from different positions at their own pace. It
does not transform or analyse data -- it only moves it.

Flink is a stream processing engine. It reads from Kafka, runs stateful
computations (fraud rules, window aggregations), and writes results back.
Flink maintains operator state across millions of events, manages event-time
watermarks, and recovers from failures using checkpoints.

In short: Kafka is the highway; Flink is the factory on the highway.

---

## Fraud Detection Rules

| Rule | Name                    | Condition                                          | Risk Score  |
|------|-------------------------|----------------------------------------------------|-------------|
| R1   | High-Value Transaction  | Single transaction exceeds $10,000                 | 50-100      |
| R2   | High Velocity           | More than 5 transactions in a 60-second window     | 40-100      |
| R3   | High Aggregate Spend    | Total spend exceeds $50,000 in a 10-minute window  | 60-100      |
| R4   | Night Owl               | Transaction between 01:00-04:00 AND amount > $3K   | 70          |
| R5   | Rapid Escalation        | Current amount more than 3x the previous amount    | 50-100      |

Rules R1, R2, R4, and R5 are implemented in a `KeyedProcessFunction` using
`ValueState` and `ListState`. Rule R3 uses `TumblingEventTimeWindows`.

---

## Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose)
- No Python, no Java, no virtual environment needed

---

## Quick Start

**1. Clone or download this tutorial folder.**

**2. Start the full pipeline:**

```bash
docker-compose up --build
```

This command starts all six services. The first run takes 5-10 minutes
because Docker builds the Flink image (downloads the Kafka connector JAR
and installs PyFlink). Subsequent runs use the cached image and start
in under a minute.

**3. Open the dashboard:**

```
http://localhost:8050
```

Alerts begin appearing within a few seconds once all services are running.

**4. Open the Flink Web UI (optional):**

```
http://localhost:8081
```

Shows the running job, operator graph, throughput, and checkpoint history.

**5. Stop everything:**

```bash
docker-compose down
```

---

## What Happens on Startup

1. Kafka starts and waits until healthy.
2. `init-kafka` creates the `transactions` and `fraud-alerts` topics, then exits.
3. Flink JobManager and TaskManager start.
4. `detector` waits for the Flink cluster, then submits the PyFlink job via
   `flink run --python fraud_detector.py`.
5. `generator` starts publishing transactions to Kafka.
6. The Flink job reads from Kafka, applies fraud rules, and writes alerts
   back to Kafka.
7. The dashboard consumes from `fraud-alerts` and updates every 2 seconds.

---

## Streaming Concepts Demonstrated

### KafkaSource (unbounded stream source)

The PyFlink job reads from the `transactions` topic as an unbounded stream:

```python
source = (
    KafkaSource.builder()
    .set_bootstrap_servers("kafka:9092")
    .set_topics("transactions")
    .set_group_id("fraud-detector-group")
    .set_starting_offsets(KafkaOffsetsInitializer.latest())
    .set_value_only_deserializer(SimpleStringSchema())
    .build()
)
raw_stream = env.from_source(
    source, WatermarkStrategy.no_watermarks(), "KafkaSource[transactions]"
)
```

`KafkaSource` is a real unbounded source -- the job never ends until
explicitly cancelled. This is what allows Flink to maintain state and
process events continuously without restarting.

### Event Time and Watermarks

The pipeline uses event time (the `event_time` field embedded in each
transaction) rather than processing time (when Flink received the message).

```python
watermark_strategy = (
    WatermarkStrategy
    .for_bounded_out_of_orderness(Duration.of_seconds(5))
    .with_timestamp_assigner(TransactionTimestampAssigner())
)
```

`for_bounded_out_of_orderness(5s)` means:
- Watermark = max(event_time seen so far) - 5000ms
- Events arriving up to 5 seconds late are still processed correctly
- Windows fire when the watermark passes their end boundary

### KeyedProcessFunction (Rules R1, R2, R4, R5)

The `FraudDetectionFunction` processes one event at a time, keyed by
`customer_id`. Flink guarantees that all events for the same customer
always go to the same parallel task, making per-customer state consistent.

State is declared in `open()` and accessed in `process_element()`:

```python
def open(self, runtime_context):
    last_desc = ValueStateDescriptor("last_amount", Types.FLOAT())
    last_desc.enable_time_to_live(ttl_config)
    self.last_amount_state = runtime_context.get_state(last_desc)

    recent_desc = ListStateDescriptor("recent_txns", Types.STRING())
    recent_desc.enable_time_to_live(ttl_config)
    self.recent_txns_state = runtime_context.get_list_state(recent_desc)
```

`StateTtlConfig` with `Time.hours(1)` means state for inactive customers
is automatically garbage-collected after 1 hour, preventing unbounded
memory growth over a long-running job.

### Tumbling Event-Time Windows (Rule R3)

Rule R3 uses a 10-minute tumbling window per customer to detect high
aggregate spend:

```python
window_alerts = (
    keyed_stream
    .window(TumblingEventTimeWindows.of(Time.minutes(10)))
    .process(AggregateWindowFunction(), output_type=Types.STRING())
)
```

Tumbling windows are non-overlapping fixed-size buckets:
```
[00:00 - 00:10)   [00:10 - 00:20)   [00:20 - 00:30) ...
```

The window fires when the watermark advances past the window end boundary.
Each event belongs to exactly one window.

### KafkaSink (streaming output)

Alerts are written to the `fraud-alerts` Kafka topic:

```python
sink = (
    KafkaSink.builder()
    .set_bootstrap_servers("kafka:9092")
    .set_record_serializer(
        KafkaRecordSerializationSchema.builder()
        .set_topic("fraud-alerts")
        .set_value_serialization_schema(SimpleStringSchema())
        .build()
    )
    .build()
)
all_alerts.sink_to(sink)
```

The dashboard is a Kafka consumer on this topic. Because Kafka delivers
messages with low latency, alerts appear on the dashboard within
milliseconds of being produced by Flink.

### Checkpointing

```python
env.enable_checkpointing(30_000)
```

Flink snapshots all operator state (ValueState, ListState, window contents)
to durable storage every 30 seconds. If the job crashes, Flink restarts
from the last checkpoint -- no state is lost, and no messages need to be
reprocessed beyond the checkpoint boundary.

---

## Useful Commands

```bash
# Follow logs for a specific service
docker-compose logs -f detector
docker-compose logs -f generator
docker-compose logs -f dashboard

# Restart only the detector (e.g. after editing fraud_detector.py)
docker-compose restart detector

# List Kafka topics
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

# Tail the transactions topic
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic transactions --from-beginning

# Tail the fraud-alerts topic
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic fraud-alerts --from-beginning
```

---

## Project Structure

```
08-Kafka-Flink-Fraud/
├── docker-compose.yml       Service definitions
├── Dockerfile.flink         Flink 1.18 + Python 3.11 + Kafka connector JAR
├── Dockerfile.generator     Python 3.11 + kafka-python
├── Dockerfile.dashboard     Python 3.11 + Flask + kafka-python
├── src/
│   ├── data_generator.py    Kafka producer (simulated transactions)
│   └── fraud_detector.py    PyFlink job (fraud detection pipeline)
└── dashboard/
    ├── server.py            Flask server + Kafka consumer
    └── index.html           Live dashboard UI
```

---

## Exercises

1. Add a new fraud rule R6: flag customers who transact in more than
   3 different cities within 10 minutes. What state type would you use?

2. Increase `parallelism.default` in `docker-compose.yml` from 1 to 2.
   What happens to the Flink Web UI? Why do some operators have
   two parallel instances?

3. Change the `KafkaSource` to use `KafkaOffsetsInitializer.earliest()`
   instead of `latest()`. Restart the detector service. What changes?

4. Add a second TaskManager to `docker-compose.yml`. How does Flink
   distribute the job across two task managers?

5. Modify the dashboard to show a per-rule alert rate chart (alerts per
   minute, broken down by rule ID) in addition to the total alerts chart.
