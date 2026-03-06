"""
fraud_detector.py — PyFlink Fraud Detection Pipeline
=====================================================
This is the heart of the tutorial. It implements a full streaming
fraud detection pipeline using PyFlink, demonstrating:

  1. Stream source (JSONL file tail)
  2. Timestamp assignment & watermark generation (event time)
  3. KeyBy partitioning (per customer)
  4. Stateful fraud detection (ValueState, ListState)
  5. Window aggregation (tumbling windows for Rule R3)
  6. Multi-stream union into a single alert sink

Run:
    python fraud_detector.py

Prerequisites:
    pip install apache-flink==2.2.0 --no-deps
"""

import json
import os
from datetime import datetime

# ── PyFlink imports ──────────────────────────────────────────────────────────
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.functions import (
    MapFunction,
    KeyedProcessFunction,
    RuntimeContext,
)
from pyflink.datastream.state import (
    ValueStateDescriptor,
    ListStateDescriptor,
    StateTtlConfig,
)
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.datastream.functions import ProcessWindowFunction
from pyflink.common import Time, Types, WatermarkStrategy, Duration
from pyflink.common.watermark_strategy import TimestampAssigner
from pyflink.datastream.connectors.file_system import (
    FileSource, FileSink, StreamFormat, OutputFileConfig, Encoder
)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: DATA MODEL
# ─────────────────────────────────────────────────────────────────────────────

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

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}


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


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: PARSING
# ─────────────────────────────────────────────────────────────────────────────

class ParseTransaction(MapFunction):
    """
    MapFunction: raw JSON string → Transaction object (serialized as string).

    Why serialize back to string?
    PyFlink transfers data between operators as bytes. We use JSON strings
    as a simple, portable serialization format throughout this pipeline.
    In production, use Avro or Protobuf for efficiency.
    """

    def map(self, raw: str) -> str:
        try:
            d = json.loads(raw.strip())
            # Validate required fields
            if not all(k in d for k in ("transaction_id", "customer_id", "amount", "event_time")):
                return None
            return json.dumps(d)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None   # Drop malformed records


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: WATERMARK STRATEGY
# ─────────────────────────────────────────────────────────────────────────────

class TransactionTimestampAssigner(TimestampAssigner):
    """
    Extracts event_time from each transaction record for Flink's
    event-time clock.

    This tells Flink: "the timestamp for THIS record is the event_time
    field embedded in the JSON, not the current wall clock."

    Flink then computes watermarks based on the maximum event_time seen
    so far minus the configured allowed lateness (5 seconds here).

    ─── Why is this important? ────────────────────────────────────────────
    Imagine two transactions:
       TXN-A: event_time = 10:00:01, arrives at Flink at 10:00:06 (5s late)
       TXN-B: event_time = 10:00:02, arrives at Flink at 10:00:03 (on time)

    Without event time, Flink would process TXN-B first and TXN-A second,
    which reverses their actual order and breaks velocity detection.

    With event time + this assigner, Flink correctly knows TXN-A happened
    first (at 10:00:01) even though it arrived later.
    """

    def extract_timestamp(self, value: str, record_timestamp: int) -> int:
        try:
            d = json.loads(value)
            return int(d["event_time"])    # milliseconds since epoch
        except Exception:
            return record_timestamp        # fall back to ingestion time


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: STATEFUL FRAUD DETECTION (Rules R1, R2, R4, R5)
# ─────────────────────────────────────────────────────────────────────────────

class FraudDetectionFunction(KeyedProcessFunction):
    """
    The core fraud detection operator.

    This is a KeyedProcessFunction: it processes one event at a time,
    keyed by customer_id. Each customer_id has its OWN independent state.

    ─── State Used ──────────────────────────────────────────────────────────
    last_amount_state  (ValueState[float]):
        The amount of the most recent transaction for this customer.
        Used for Rule R5 (rapid escalation detection).

    recent_txns_state  (ListState[str]):
        A list of serialized recent transactions (JSON strings) for this
        customer, kept for the past TTL window.
        Used for Rule R2 (velocity: count transactions in last 60 seconds).

    ─── State TTL ───────────────────────────────────────────────────────────
    Both state entries have a TTL of 1 hour. After 1 hour of inactivity
    for a customer, their state is automatically garbage-collected.
    This prevents unbounded state growth as the customer base grows.

    Without TTL: state would accumulate for all customers ever seen.
    With TTL=1h: only active customers in the last hour consume state memory.
    """

    def open(self, runtime_context: RuntimeContext):
        """
        Called once when the operator is initialized.
        This is where we declare and register state descriptors.
        State descriptors tell Flink:
          - What to name this piece of state (for checkpointing/recovery)
          - What type the state holds
          - Any TTL (time-to-live) configuration
        """

        # ── TTL configuration ──────────────────────────────────────────────
        # Keep state for 1 hour; expire on last write; never return expired values
        ttl_config = (
            StateTtlConfig
            .new_builder(Time.hours(1))
            .set_update_type(StateTtlConfig.UpdateType.OnCreateAndWrite)
            .set_state_visibility(
                StateTtlConfig.StateVisibility.NeverReturnExpired)
            .build()
        )

        # ── ValueState: last transaction amount ────────────────────────────
        # Stores exactly one float per customer.
        # Access: self.last_amount_state.value()  / .update(new_val)
        last_amount_desc = ValueStateDescriptor("last_amount", Types.FLOAT())
        last_amount_desc.enable_time_to_live(ttl_config)
        self.last_amount_state = runtime_context.get_state(last_amount_desc)

        # ── ListState: recent transaction JSON strings ─────────────────────
        # Stores a list of JSON strings (one per recent transaction).
        # Access: iterate directly / .add(item) / .clear()
        recent_desc = ListStateDescriptor("recent_transactions", Types.STRING())
        recent_desc.enable_time_to_live(ttl_config)
        self.recent_txns_state = runtime_context.get_list_state(recent_desc)

    def process_element(self, value: str, ctx: KeyedProcessFunction.Context):
        """
        Called once for each transaction event.

        `ctx` provides:
          - ctx.timestamp()           → event time of this record (ms)
          - ctx.timer_service()       → register event-time / processing-time timers
          - ctx.current_watermark()  → current watermark (event time progress)
        """
        try:
            d     = json.loads(value)
            txn   = Transaction(d)
        except Exception:
            return

        alerts = []

        # ── Rule R1: High-Value Transaction ────────────────────────────────
        if txn.amount > 10_000:
            risk_score = min(100.0, 50.0 + (txn.amount - 10_000) / 1_000)
            alerts.append(FraudAlert(
                txn,
                rule_id="R1",
                rule_name="High-Value Transaction",
                risk_score=risk_score,
                details=f"Amount ${txn.amount:,.2f} exceeds threshold of $10,000",
            ))

        # ── Rule R2: Velocity (> 5 transactions in 60 seconds) ─────────────
        #
        # We use ListState to accumulate recent transactions.
        # On each event, we:
        #   1. Add the current event_time to the list
        #   2. Filter out entries older than 60 seconds
        #   3. If the count is > 5, emit a velocity alert
        #
        # Why ListState and not a window?
        # Keyed windows fire on window boundaries (e.g., every 60s), but we
        # want a SLIDING check: "in the 60 seconds BEFORE this transaction".
        # ListState gives us full control over the time window per event.

        current_event_time = txn.event_time   # ms
        cutoff_ms = current_event_time - 60_000    # 60 seconds ago

        # Retrieve existing recent transaction timestamps
        existing = list(self.recent_txns_state or [])
        # Each entry is a JSON string: {"ts": <ms>, ...}
        recent = []
        for entry_str in existing:
            try:
                entry = json.loads(entry_str)
                if entry["ts"] >= cutoff_ms:
                    recent.append(entry)
            except Exception:
                pass

        recent.append({"ts": current_event_time, "amount": txn.amount})

        # Update state with pruned + new list
        self.recent_txns_state.clear()
        for r in recent:
            self.recent_txns_state.add(json.dumps(r))

        if len(recent) > 5:
            alerts.append(FraudAlert(
                txn,
                rule_id="R2",
                rule_name="High Transaction Velocity",
                risk_score=min(100.0, 40.0 + (len(recent) - 5) * 8.0),
                details=f"{len(recent)} transactions in last 60 seconds",
            ))

        # ── Rule R4: Night Owl (01:00–04:00 + amount > $3,000) ─────────────
        if 1 <= txn.hour <= 4 and txn.amount > 3_000:
            alerts.append(FraudAlert(
                txn,
                rule_id="R4",
                rule_name="Unusual Hour + High Amount",
                risk_score=70.0,
                details=f"${txn.amount:,.2f} transaction at {txn.hour:02d}:00",
            ))

        # ── Rule R5: Rapid Escalation ───────────────────────────────────────
        # Compare this transaction's amount to the last one for this customer.
        # If this amount is > 3× the last, flag it.
        #
        # ValueState stores exactly one value: the last transaction's amount.
        # .value() returns None if no previous transaction has been seen.

        last_amount = self.last_amount_state.value()
        if last_amount is not None and last_amount > 0:
            ratio = txn.amount / last_amount
            if ratio > 3.0:
                alerts.append(FraudAlert(
                    txn,
                    rule_id="R5",
                    rule_name="Rapid Amount Escalation",
                    risk_score=min(100.0, 50.0 + ratio * 5),
                    details=(f"Amount ${txn.amount:,.2f} is {ratio:.1f}× "
                             f"previous ${last_amount:,.2f}"),
                ))

        # Update last_amount_state with this transaction's amount
        self.last_amount_state.update(txn.amount)

        # ── Emit all alerts ─────────────────────────────────────────────────
        for alert in alerts:
            yield alert.to_json()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: WINDOW AGGREGATION (Rule R3 — Aggregate Amount)
# ─────────────────────────────────────────────────────────────────────────────

class AggregateWindowFunction(ProcessWindowFunction):
    """
    Rule R3: Total spend in a 10-minute tumbling window > $50,000.

    This is implemented as a window function rather than keyed process state
    because it naturally maps to a time-bounded aggregate: sum all amounts
    in a fixed 10-minute bucket per customer.

    ─── Tumbling vs Sliding Windows ─────────────────────────────────────────
    Tumbling window (what we use):
      [00:00 – 00:10)  [00:10 – 00:20)  [00:20 – 00:30)  ...
      Each event belongs to exactly ONE window.
      Good for: "total spend in hour", "transactions per minute"

    Sliding window:
      [00:00 – 00:10)  [00:05 – 00:15)  [00:10 – 00:20)  ...
      Each event may belong to MULTIPLE overlapping windows.
      Good for: "rolling 10-minute total checked every 5 minutes"
      More expensive: each event processed window_size/slide times.

    ─── Event Time and Watermarks ────────────────────────────────────────────
    Windows fire based on event time progress tracked by watermarks.
    The 10-minute window [10:00 – 10:10) fires when the watermark passes
    10:10:00 (i.e., when Flink has seen events timestamped past 10:10
    minus the allowed lateness). This means a window can be slightly
    late to close if data is arriving slowly — a feature, not a bug.
    """

    def process(self,
                key: str,
                context: ProcessWindowFunction.Context,
                elements) -> list:
        """
        `elements` contains all Transaction JSON strings in this window.
        `key` is the customer_id.
        `context.window()` gives the window boundaries.
        """
        total_amount = 0.0
        txn_count    = 0
        last_txn     = None

        for elem in elements:
            try:
                d = json.loads(elem)
                total_amount += float(d["amount"])
                txn_count += 1
                last_txn = d
            except Exception:
                pass

        if total_amount > 50_000 and last_txn is not None:
            window_start = context.window().start
            window_end   = context.window().end
            alert = {
                "transaction_id": last_txn["transaction_id"],
                "customer_id":    key,
                "amount":         total_amount,
                "city":           last_txn.get("city", ""),
                "event_time":     last_txn["event_time"],
                "rule_id":        "R3",
                "rule_name":      "High Aggregate Spend",
                "risk_score":     min(100.0, 60.0 + (total_amount - 50_000) / 1_000),
                "details":        (
                    f"{txn_count} transactions totalling "
                    f"${total_amount:,.2f} in window "
                    f"[{window_start} – {window_end}]"
                ),
                "alert_time": int(datetime.now().timestamp() * 1000),
            }
            return [json.dumps(alert)]

        return []


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: PIPELINE ASSEMBLY
# ─────────────────────────────────────────────────────────────────────────────

def build_pipeline(input_file: str, alert_file: str):
    """
    Assembles and returns the Flink StreamExecutionEnvironment
    with the full fraud detection pipeline wired up.

    Pipeline topology:
                                          ┌─ FraudDetectionFunction (R1,R2,R4,R5) ──┐
    Source ──▶ Filter(non-null) ──▶ keyBy ─┤                                          ├─▶ Union ──▶ Sink
                                          └─ TumblingWindow (R3) ───────────────────┘
    """

    # ── Environment setup ─────────────────────────────────────────────────
    env = StreamExecutionEnvironment.get_execution_environment()

    # In Flink 2.0+, event time is the ONLY supported time characteristic.
    # The old set_stream_time_characteristic(TimeCharacteristic.EventTime)
    # call has been removed — event time is now always active by default.
    # Watermarks are still configured per-source via WatermarkStrategy (unchanged).

    # Set default parallelism: how many parallel copies of each operator to run.
    # For local development, 2 is a good default.
    env.set_parallelism(1)  # FileSource with text_line_format is not splittable

    # Enable checkpointing every 30 seconds (fault tolerance)
    env.enable_checkpointing(30_000)

    # ── Source ─────────────────────────────────────────────────────────────
    # Read from a JSONL file. In production, replace with a Kafka source:
    #
    #   from pyflink.datastream.connectors.kafka import KafkaSource
    #   source = KafkaSource.builder()
    #       .set_bootstrap_servers("localhost:9092")
    #       .set_topics("transactions")
    #       .set_group_id("fraud-detector")
    #       .set_value_only_deserializer(SimpleStringSchema())
    #       .build()
    #   raw_stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "Kafka")

    # Read transactions from file using Python, then feed to Flink via from_collection.
    # FileSource.monitor_continuously() monitors for new files added to a directory,
    # not new lines appended to a single file — not suitable for a tutorial setting.
    # In production, replace this with a KafkaSource for true streaming.
    with open(input_file, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
    print(f"  Loaded {len(lines)} transactions from file")
    raw_stream = env.from_collection(lines, type_info=Types.STRING())

    # ── Parse ──────────────────────────────────────────────────────────────
    parsed_stream = (
        raw_stream
        .map(ParseTransaction(), output_type=Types.STRING())
        .filter(lambda x: x is not None)
    )

    # ── Assign Timestamps & Watermarks ─────────────────────────────────────
    #
    # WatermarkStrategy.for_bounded_out_of_orderness(Duration.of_seconds(5)):
    #   Creates a watermark strategy that tolerates up to 5 seconds of
    #   out-of-orderness. This means:
    #     - Watermark = max(event_time_seen) - 5_000ms
    #     - Events arriving up to 5 seconds late are still processed correctly
    #     - Events arriving > 5 seconds late are "late data" (dropped or side-output)
    #
    # with_timestamp_assigner(TransactionTimestampAssigner()):
    #   Teaches Flink how to extract the event time from each record.
    #   Without this, Flink would use ingestion time as the "event time",
    #   which defeats the purpose.

    watermark_strategy = (
        WatermarkStrategy
        .for_bounded_out_of_orderness(Duration.of_seconds(5))
        .with_timestamp_assigner(TransactionTimestampAssigner())
    )

    timed_stream = parsed_stream.assign_timestamps_and_watermarks(
        watermark_strategy
    )

    # ── KeyBy customer_id ──────────────────────────────────────────────────
    # This partitions the stream so all events with the same customer_id
    # always go to the same task. This is what makes state meaningful:
    # the FraudDetectionFunction can maintain per-customer history because
    # it is guaranteed to always see ALL events for a given customer.
    keyed_stream = timed_stream.key_by(
        lambda x: json.loads(x)["customer_id"],
        key_type=Types.STRING()
    )

    # ── Rule R1, R2, R4, R5: Stateful Per-Customer Detection ───────────────
    rule_r1_r2_r4_r5_alerts = (
        keyed_stream
        .process(FraudDetectionFunction(), output_type=Types.STRING())
    )

    # ── Rule R3: Tumbling 10-minute Window Aggregate ───────────────────────
    # Steps:
    #   1. window() — group events into 10-minute buckets by event time
    #   2. process() — for each completed window, sum amounts and check threshold
    rule_r3_alerts = (
        keyed_stream
        .window(TumblingEventTimeWindows.of(Time.minutes(10)))
        .process(AggregateWindowFunction(), output_type=Types.STRING())
    )

    # ── Union all alert streams ─────────────────────────────────────────────
    all_alerts = rule_r1_r2_r4_r5_alerts.union(rule_r3_alerts)

    # ── Sink: write alerts to JSONL file ────────────────────────────────────
    # We use a simple MapFunction sink instead of FileSink.
    # FileSink writes to a directory of part-files (e.g. alerts.jsonl/.part-0-0),
    # which the dashboard server cannot read as a flat file.
    # In production: write to a Kafka topic "fraud-alerts" or Elasticsearch.

    class WriteAlertSink(MapFunction):
        def __init__(self, path):
            self.path = path
        def open(self, runtime_context):
            import threading
            self._lock = threading.Lock()
        def map(self, value):
            with self._lock:
                with open(self.path, "a") as f:
                    f.write(value + "
")
            return value

    all_alerts.map(WriteAlertSink(alert_file), output_type=Types.STRING()).print()

    return env


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
    INPUT_FILE  = os.path.join(BASE_DIR, "..", "data", "transactions.jsonl")
    ALERT_FILE  = os.path.join(BASE_DIR, "..", "data", "alerts.jsonl")

    os.makedirs(os.path.join(BASE_DIR, "..", "data"), exist_ok=True)

    print("=" * 60)
    print("  PyFlink Fraud Detection Pipeline")
    print("=" * 60)
    print(f"  Input:  {INPUT_FILE}")
    print(f"  Alerts: {ALERT_FILE}")
    print("=" * 60)
    print()
    print("Concepts demonstrated:")
    print("  ✓ Event time vs processing time")
    print("  ✓ Bounded out-of-orderness watermarks (5s latency)")
    print("  ✓ Keyed state (ValueState + ListState) with TTL")
    print("  ✓ KeyedProcessFunction for per-customer rules")
    print("  ✓ TumblingEventTimeWindows for aggregate rules")
    print("  ✓ Multi-stream union")
    print("  ✓ Checkpointing (30s interval)")
    print()

    env = build_pipeline(INPUT_FILE, ALERT_FILE)

    print("Submitting Flink job...")
    env.execute("Fraud Detection Pipeline")
