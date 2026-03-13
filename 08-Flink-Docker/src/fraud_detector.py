"""
fraud_detector.py -- PyFlink Fraud Detection Pipeline
======================================================
A real PyFlink streaming job that reads from Kafka, applies stateful fraud
detection rules, and writes alerts back to Kafka.

This job is submitted to a running Flink cluster via:
    flink run --python src/fraud_detector.py

Pipeline topology:

    KafkaSource("transactions")
        --> parse JSON
        --> assign timestamps + watermarks (event time)
        --> keyBy(customer_id)
            --> FraudDetectionFunction      (Rules R1, R2, R4, R5)  --+
            --> TumblingEventTimeWindows    (Rule R3)                 --+--> union --> KafkaSink("fraud-alerts")

Concepts demonstrated
---------------------
- KafkaSource: unbounded stream source (replaces FileSource in production)
- Event time + bounded out-of-orderness watermarks
- KeyedProcessFunction: stateful per-customer fraud rules
- ValueState: stores last transaction amount per customer (Rule R5)
- ListState: stores recent transaction history per customer (Rule R2)
- StateTtlConfig: automatic state expiry after 1 hour of inactivity
- TumblingEventTimeWindows: aggregate rule over a fixed time bucket (Rule R3)
- Multi-stream union: merge alert streams from all rules
- KafkaSink: writes alerts to "fraud-alerts" topic for the dashboard

Configuration
-------------
KAFKA_BOOTSTRAP  Kafka broker address (default: kafka:9092)
TRANSACTIONS_TOPIC   Input topic  (default: transactions)
ALERTS_TOPIC         Output topic (default: fraud-alerts)
"""

import json
import os
from datetime import datetime

# -- PyFlink imports ----------------------------------------------------------
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.functions import (
    MapFunction,
    KeyedProcessFunction,
    RuntimeContext,
    ProcessWindowFunction,
)
from pyflink.datastream.state import (
    ValueStateDescriptor,
    ListStateDescriptor,
    StateTtlConfig,
)
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.common import Time, Types, WatermarkStrategy, Duration
from pyflink.common.watermark_strategy import TimestampAssigner
from pyflink.datastream.connectors.kafka import (
    KafkaSource,
    KafkaSink,
    KafkaOffsetsInitializer,
    KafkaRecordSerializationSchema,
)
from pyflink.common.serialization import SimpleStringSchema


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

KAFKA_BOOTSTRAP    = os.getenv("KAFKA_BOOTSTRAP",    "kafka:9092")
TRANSACTIONS_TOPIC = os.getenv("TRANSACTIONS_TOPIC", "transactions")
ALERTS_TOPIC       = os.getenv("ALERTS_TOPIC",       "fraud-alerts")


# -----------------------------------------------------------------------------
# SECTION 1: DATA MODEL
# -----------------------------------------------------------------------------

class Transaction:
    """Plain Python object representing one parsed transaction."""
    __slots__ = [
        "transaction_id", "customer_id", "amount",
        "merchant", "city", "event_time", "hour"
    ]

    def __init__(self, d: dict):
        self.transaction_id = d["transaction_id"]
        self.customer_id    = d["customer_id"]
        self.amount         = float(d["amount"])
        self.merchant       = d.get("merchant", "")
        self.city           = d.get("city", "")
        self.event_time     = int(d["event_time"])   # Unix ms
        self.hour           = int(d.get("hour", 0))


class FraudAlert:
    """A fraud alert emitted by the detection pipeline."""

    def __init__(self, txn: Transaction, rule_id: str,
                 rule_name: str, risk_score: float, details: str):
        self.transaction_id = txn.transaction_id
        self.customer_id    = txn.customer_id
        self.amount         = txn.amount
        self.city           = txn.city
        self.event_time     = txn.event_time
        self.rule_id        = rule_id
        self.rule_name      = rule_name
        self.risk_score     = round(risk_score, 2)
        self.details        = details
        self.alert_time     = int(datetime.now().timestamp() * 1000)

    def to_json(self) -> str:
        return json.dumps({
            "transaction_id": self.transaction_id,
            "customer_id":    self.customer_id,
            "amount":         self.amount,
            "city":           self.city,
            "event_time":     self.event_time,
            "rule_id":        self.rule_id,
            "rule_name":      self.rule_name,
            "risk_score":     self.risk_score,
            "details":        self.details,
            "alert_time":     self.alert_time,
        })


# -----------------------------------------------------------------------------
# SECTION 2: PARSING
# -----------------------------------------------------------------------------

class ParseTransaction(MapFunction):
    """
    MapFunction: raw Kafka message (JSON string) --> validated JSON string.

    Malformed or incomplete messages are dropped (return None) and filtered
    downstream. In production, route them to a dead-letter topic instead.
    """

    def map(self, raw: str) -> str:
        try:
            d = json.loads(raw.strip())
            if not all(k in d for k in
                       ("transaction_id", "customer_id", "amount", "event_time")):
                return None
            return json.dumps(d)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None


# -----------------------------------------------------------------------------
# SECTION 3: WATERMARK STRATEGY
# -----------------------------------------------------------------------------

class TransactionTimestampAssigner(TimestampAssigner):
    """
    Extracts event_time from each transaction for Flink's event-time clock.

    Why event time matters
    ----------------------
    Kafka delivers messages in roughly arrival order, but network delays
    and producer batching can cause out-of-orderness. Using event_time
    (when the transaction actually occurred) instead of ingestion time
    (when Flink received it) ensures fraud rules based on time windows
    are evaluated correctly even when messages arrive slightly late.

    Watermark formula: watermark = max(event_time_seen) - 5000ms
    This means:
      - Events arriving up to 5 seconds late are still processed
      - Events arriving more than 5 seconds late are treated as late data
      - Windows fire when the watermark passes their end boundary
    """

    def extract_timestamp(self, value: str, record_timestamp: int) -> int:
        try:
            return int(json.loads(value)["event_time"])
        except Exception:
            return record_timestamp


# -----------------------------------------------------------------------------
# SECTION 4: STATEFUL FRAUD DETECTION (Rules R1, R2, R4, R5)
# -----------------------------------------------------------------------------

class FraudDetectionFunction(KeyedProcessFunction):
    """
    Core fraud detection operator.

    This is a KeyedProcessFunction keyed by customer_id. Flink guarantees
    that all events for the same customer_id are routed to the same parallel
    task, so state is always consistent per customer.

    State
    -----
    last_amount_state  ValueState[float]
        Amount of the most recent transaction for this customer.
        Used by Rule R5 (rapid escalation).

    recent_txns_state  ListState[str]
        JSON-serialized recent transactions within the last 60 seconds.
        Used by Rule R2 (velocity check).

    State TTL
    ---------
    Both states expire after 1 hour of inactivity per customer, preventing
    unbounded memory growth in long-running jobs. StateTtlConfig handles
    this automatically in the background without any explicit cleanup code.
    """

    def open(self, runtime_context: RuntimeContext):
        """
        Called once per task when the operator initializes.
        All state descriptors must be registered here.
        """
        ttl_config = (
            StateTtlConfig
            .new_builder(Time.hours(1))
            .set_update_type(StateTtlConfig.UpdateType.OnCreateAndWrite)
            .set_state_visibility(
                StateTtlConfig.StateVisibility.NeverReturnExpired)
            .build()
        )

        last_desc = ValueStateDescriptor("last_amount", Types.FLOAT())
        last_desc.enable_time_to_live(ttl_config)
        self.last_amount_state = runtime_context.get_state(last_desc)

        recent_desc = ListStateDescriptor("recent_txns", Types.STRING())
        recent_desc.enable_time_to_live(ttl_config)
        self.recent_txns_state = runtime_context.get_list_state(recent_desc)

    def process_element(self, value: str, ctx: KeyedProcessFunction.Context):
        """
        Called once for each transaction event in the stream.

        Evaluates all stateful rules against the current transaction and
        emits FraudAlert JSON strings for any rules that fire.
        """
        try:
            d   = json.loads(value)
            txn = Transaction(d)
        except Exception:
            return

        # -- Rule R1: High-Value Transaction ----------------------------------
        # A single transaction exceeds $10,000.
        # Stateless: no prior history needed, fires immediately.
        if txn.amount > 10_000:
            risk = min(100.0, 50.0 + (txn.amount - 10_000) / 1_000)
            yield FraudAlert(
                txn, "R1", "High-Value Transaction", risk,
                f"Amount ${txn.amount:,.2f} exceeds $10,000 threshold",
            ).to_json()

        # -- Rule R2: Velocity Check (> 5 transactions in 60 seconds) ---------
        # Uses ListState to maintain a sliding window of recent events.
        #
        # On each event:
        #   1. Load existing entries from state
        #   2. Prune entries older than 60 seconds
        #   3. Append this event
        #   4. Save the pruned list back to state
        #   5. Fire alert if count exceeds threshold
        #
        # Why ListState instead of a Flink window?
        # TumblingEventTimeWindows fire at fixed boundaries (e.g. every 60s).
        # Rule R2 needs a sliding check: "in the 60 seconds BEFORE this event".
        # ListState lets us do a per-event sliding look-back without windowing.
        cutoff_ms = txn.event_time - 60_000
        recent = []
        for entry_str in (self.recent_txns_state or []):
            try:
                entry = json.loads(entry_str)
                if entry["ts"] >= cutoff_ms:
                    recent.append(entry)
            except Exception:
                pass

        recent.append({"ts": txn.event_time, "amount": txn.amount})
        self.recent_txns_state.clear()
        for r in recent:
            self.recent_txns_state.add(json.dumps(r))

        if len(recent) > 5:
            risk = min(100.0, 40.0 + (len(recent) - 5) * 8.0)
            yield FraudAlert(
                txn, "R2", "High Transaction Velocity", risk,
                f"{len(recent)} transactions in the last 60 seconds",
            ).to_json()

        # -- Rule R4: Night Owl + High Amount ---------------------------------
        # Stateless: fires when hour is 01:00-04:00 and amount > $3,000.
        if 1 <= txn.hour <= 4 and txn.amount > 3_000:
            yield FraudAlert(
                txn, "R4", "Unusual Hour + High Amount", 70.0,
                f"${txn.amount:,.2f} transaction at {txn.hour:02d}:00",
            ).to_json()

        # -- Rule R5: Rapid Amount Escalation ---------------------------------
        # Uses ValueState to compare against the previous transaction amount.
        # Fires if the current amount is more than 3x the previous amount.
        last_amount = self.last_amount_state.value()
        if last_amount is not None and last_amount > 0:
            ratio = txn.amount / last_amount
            if ratio > 3.0:
                risk = min(100.0, 50.0 + ratio * 5)
                yield FraudAlert(
                    txn, "R5", "Rapid Amount Escalation", risk,
                    f"${txn.amount:,.2f} is {ratio:.1f}x previous "
                    f"${last_amount:,.2f}",
                ).to_json()

        self.last_amount_state.update(txn.amount)


# -----------------------------------------------------------------------------
# SECTION 5: WINDOW AGGREGATION (Rule R3)
# -----------------------------------------------------------------------------

class AggregateWindowFunction(ProcessWindowFunction):
    """
    Rule R3: Total spend exceeds $50,000 in a 10-minute tumbling window.

    Tumbling vs Sliding Windows
    ---------------------------
    Tumbling (used here):
      Non-overlapping, fixed-size buckets.
      [00:00-00:10)  [00:10-00:20)  [00:20-00:30) ...
      Each event belongs to exactly one window.
      Lower memory cost: one window active per customer at a time.

    Sliding:
      Overlapping windows where each event may belong to multiple windows.
      [00:00-00:10)  [00:05-00:15)  [00:10-00:20) ...
      More expensive: each event is processed window_size/slide times.

    When does this window fire?
    ---------------------------
    Flink fires the window when the watermark passes the window end boundary.
    For a [10:00-10:10) window, the watermark must reach 10:10:00 (minus
    allowed lateness) before the window is evaluated. In a live stream with
    active traffic, this happens naturally a few seconds after 10:10.
    """

    def process(self, key: str,
                context: ProcessWindowFunction.Context,
                elements) -> list:
        total  = 0.0
        count  = 0
        last_d = None

        for elem in elements:
            try:
                d = json.loads(elem)
                total  += float(d["amount"])
                count  += 1
                last_d  = d
            except Exception:
                pass

        if total > 50_000 and last_d is not None:
            risk  = min(100.0, 60.0 + (total - 50_000) / 1_000)
            start = context.window().start
            end   = context.window().end
            alert = {
                "transaction_id": last_d["transaction_id"],
                "customer_id":    key,
                "amount":         total,
                "city":           last_d.get("city", ""),
                "event_time":     last_d["event_time"],
                "rule_id":        "R3",
                "rule_name":      "High Aggregate Spend",
                "risk_score":     risk,
                "details":        (
                    f"{count} transactions totalling ${total:,.2f} "
                    f"in 10-min window [{start} - {end}]"
                ),
                "alert_time": int(datetime.now().timestamp() * 1000),
            }
            return [json.dumps(alert)]

        return []


# -----------------------------------------------------------------------------
# SECTION 6: PIPELINE ASSEMBLY
# -----------------------------------------------------------------------------

def build_pipeline():
    """
    Assembles and executes the Flink fraud detection pipeline.

    The job runs indefinitely (unbounded Kafka source) until cancelled.
    Flink manages operator lifecycle, checkpointing, and state recovery.
    """
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    # Checkpoint every 30 seconds. If the job crashes, Flink restarts
    # from the last successful checkpoint, preserving all operator state.
    env.enable_checkpointing(30_000)

    # -- Source: KafkaSource --------------------------------------------------
    # Reads from the "transactions" topic as an unbounded stream.
    # starting_offsets=latest means the job only processes new messages
    # arriving after the job starts, not historical messages in the topic.
    #
    # In production:
    #   - Use multiple partitions for parallel consumption
    #   - Use EARLIEST offsets + checkpointing for exactly-once guarantees
    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(KAFKA_BOOTSTRAP)
        .set_topics(TRANSACTIONS_TOPIC)
        .set_group_id("fraud-detector-group")
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    raw_stream = env.from_source(
        source,
        WatermarkStrategy.no_watermarks(),   # watermarks applied after parse
        "KafkaSource[transactions]"
    )

    # -- Parse ----------------------------------------------------------------
    parsed_stream = (
        raw_stream
        .map(ParseTransaction(), output_type=Types.STRING())
        .filter(lambda x: x is not None)
    )

    # -- Assign Timestamps and Watermarks -------------------------------------
    # Apply event-time semantics AFTER parsing so we can extract event_time
    # from the JSON. for_bounded_out_of_orderness tolerates up to 5 seconds
    # of late arrival before advancing the watermark.
    watermark_strategy = (
        WatermarkStrategy
        .for_bounded_out_of_orderness(Duration.of_seconds(5))
        .with_timestamp_assigner(TransactionTimestampAssigner())
    )
    timed_stream = parsed_stream.assign_timestamps_and_watermarks(
        watermark_strategy
    )

    # -- KeyBy customer_id ----------------------------------------------------
    # All events for the same customer_id are routed to the same task.
    # This makes keyed state (per-customer history) consistent and correct.
    keyed_stream = timed_stream.key_by(
        lambda x: json.loads(x)["customer_id"],
        key_type=Types.STRING()
    )

    # -- Rules R1, R2, R4, R5: KeyedProcessFunction ---------------------------
    rule_alerts = (
        keyed_stream
        .process(FraudDetectionFunction(), output_type=Types.STRING())
    )

    # -- Rule R3: 10-minute Tumbling Window -----------------------------------
    window_alerts = (
        keyed_stream
        .window(TumblingEventTimeWindows.of(Time.minutes(10)))
        .process(AggregateWindowFunction(), output_type=Types.STRING())
    )

    # -- Union all alert streams ----------------------------------------------
    all_alerts = rule_alerts.union(window_alerts)

    # -- Sink: KafkaSink ------------------------------------------------------
    # Writes each alert as a JSON message to the "fraud-alerts" topic.
    # The dashboard consumes this topic to display alerts in real time.
    #
    # In production, also write to Elasticsearch or a data warehouse
    # for historical analysis and compliance reporting.
    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(KAFKA_BOOTSTRAP)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(ALERTS_TOPIC)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )

    all_alerts.sink_to(sink)

    # Also print to stdout for debugging (visible in docker-compose logs)
    all_alerts.print()

    print(f"Submitting Flink job: Fraud Detection Pipeline")
    print(f"  Kafka source: {KAFKA_BOOTSTRAP} / {TRANSACTIONS_TOPIC}")
    print(f"  Kafka sink:   {KAFKA_BOOTSTRAP} / {ALERTS_TOPIC}")
    env.execute("Fraud Detection Pipeline")


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  PyFlink Fraud Detection Pipeline")
    print("=" * 60)
    print()
    print("Concepts demonstrated:")
    print("  - KafkaSource: unbounded streaming input")
    print("  - Event time + bounded out-of-orderness watermarks")
    print("  - KeyedProcessFunction: stateful per-customer rules")
    print("  - ValueState + ListState with TTL (1h)")
    print("  - TumblingEventTimeWindows: aggregate rule (R3)")
    print("  - Multi-stream union")
    print("  - KafkaSink: streaming output to fraud-alerts topic")
    print("  - Checkpointing: fault tolerance (30s interval)")
    print()

    build_pipeline()
