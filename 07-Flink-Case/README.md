# Real-Time Fraud Detection with Apache Flink (PyFlink)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Concepts](#core-concepts)
   - Event Time vs Processing Time
   - Watermarks
   - State Management
4. [Flink Configuration Deep Dive](#flink-configuration)
5. [Project Setup](#project-setup)
6. [Data Generator](#data-generator)
7. [PyFlink Fraud Detection Pipeline](#pyflink-pipeline)
8. [Dashboard](#dashboard)
9. [Running the Tutorial](#running)
10. [Exercises](#exercises)

---

## 1. Overview <a name="overview"></a>

This tutorial builds a **production-style fraud detection system** using Apache Flink and PyFlink.
A continuous stream of simulated bank transactions flows through a Flink pipeline that:

- Assigns **event time** timestamps and computes **watermarks**
- Maintains **keyed state** per customer to track transaction history
- Fires fraud **alerts** when rule thresholds are exceeded
- Streams results to a **real-time management dashboard**

### Fraud Rules Implemented

| Rule ID | Name               | Logic                                                       |
|---------|--------------------|-------------------------------------------------------------|
| R1      | High-Value         | Single transaction > $10,000                               |
| R2      | Velocity           | > 5 transactions within any 60-second window               |
| R3      | Aggregate Amount   | Total spend in 10-minute tumbling window > $50,000         |
| R4      | Night Owl          | Transaction between 01:00–04:00 AND amount > $3,000        |
| R5      | Rapid Escalation   | Each successive transaction is > 3× the previous amount   |

---

## 2. Architecture <a name="architecture"></a>

```
┌─────────────────┐        ┌──────────────────────────────────────────────┐
│  data_generator │ ──────▶│              PyFlink Pipeline                │
│  (Python socket │        │                                              │
│   or file)      │        │  Source ──▶ Assign Timestamps & Watermarks  │
└─────────────────┘        │         ──▶ KeyBy(customer_id)              │
                           │         ──▶ FraudDetectionFunction (State)  │
                           │         ──▶ Window Aggregations             │
                           │         ──▶ Alert Sink                      │
                           └────────────────────┬─────────────────────────┘
                                                │
                                    ┌───────────▼──────────┐
                                    │  alerts.jsonl (file) │
                                    │  + dashboard server  │
                                    └──────────────────────┘
                                                │
                                    ┌───────────▼──────────┐
                                    │   Browser Dashboard  │
                                    │  (real-time charts)  │
                                    └──────────────────────┘
```

---

## 3. Core Concepts <a name="core-concepts"></a>

### 3.1 Event Time vs Processing Time

This is the most important conceptual distinction in stream processing.

**Processing Time** is the wall-clock time on the machine running Flink when it processes a record.

```
Event created at 10:00:00  →  arrives at Flink at 10:00:05  →  processed at 10:00:05
                                                                 ↑
                                               Processing Time = 10:00:05
```

**Event Time** is the timestamp *embedded in the event itself* — when the event actually happened in the real world.

```
Event created at 10:00:00  →  arrives at Flink at 10:00:05  →  processed at 10:00:05
         ↑
   Event Time = 10:00:00   (extracted from the event's own timestamp field)
```

**Why does this matter for fraud detection?**

Consider a mobile payment app in a subway tunnel. The customer makes 3 rapid transactions at 10:00:01, 10:00:02, 10:00:03 but the phone has no signal. The events arrive at Flink at 10:05:30, 10:05:31, 10:05:32 — all at once, 5 minutes late.

- With **processing time**, Flink sees 3 events arriving simultaneously and may flag a velocity rule.
  But it might miss true fraud that happened earlier in a different window.
- With **event time**, Flink correctly reconstructs that these 3 transactions happened within 2 seconds
  at 10:00:xx — and applies your window logic to *that* time range, giving accurate results.

**Rule of thumb:** Always use event time for fraud detection. The real-world ordering of transactions is what matters, not when your servers received them.

```python
# In PyFlink 2.x: event time is always active — no configuration needed.
# (The old set_stream_time_characteristic() was removed in Flink 2.0)
# Watermarks are configured per-source via WatermarkStrategy (see section 3.2)
env = StreamExecutionEnvironment.get_execution_environment()
```

---

### 3.2 Watermarks

Event time sounds great, but it creates a problem: **how does Flink know when a time window is "done"?**

If you're computing a 1-minute window for 10:00–10:01, Flink can't just close the window at 10:01 because late-arriving events (network delays, mobile devices coming back online) might still be coming in.

A **watermark** is Flink's answer. It is a special marker that flows through the stream saying:

> "I guarantee that all events with a timestamp ≤ T have now been seen. Any event with timestamp < T that arrives after this watermark is considered *late*."

```
Stream of events:  [T=10:00:01] [T=10:00:03] [T=09:59:58-LATE!] [T=10:00:05]
                                                     ↑
                              This arrived out of order — event time is before
                              the current watermark. Flink can either:
                              (a) drop it (simple), or
                              (b) trigger a late data side-output
```

**Bounded Out-of-Orderness Watermark** (what we use):
```
Watermark(t) = max_event_time_seen - allowed_lateness
```

If we've seen events up to T=10:00:10 and our allowed lateness is 5 seconds:
```
Watermark = 10:00:10 - 5s = 10:00:05
```
This means: we close windows up to 10:00:05, but we're still waiting for events that might be up to 5 seconds late.

```python
# In PyFlink: create a watermark strategy with 5-second tolerance
watermark_strategy = (
    WatermarkStrategy
    .for_bounded_out_of_orderness(Duration.of_seconds(5))
    .with_timestamp_assigner(TransactionTimestampAssigner())
)
```

**Choosing allowed lateness:**
- Too small → you miss legitimate late events, get incorrect fraud signals
- Too large → windows stay open too long, increasing memory usage and detection latency
- For fraud detection: 5–30 seconds is typically reasonable

---

### 3.3 State Management

State is what makes stream processing *intelligent* rather than just filtering. Without state, you can only look at one event in isolation. With state, you can ask: "Has this customer done anything suspicious in the past 10 minutes?"

Flink offers several state primitives:

| State Type    | Description                                     | Our Usage                              |
|---------------|-------------------------------------------------|----------------------------------------|
| `ValueState`  | Stores a single value per key                  | Last transaction amount per customer   |
| `ListState`   | Stores a list of values per key                | Recent N transactions per customer     |
| `MapState`    | Stores a key-value map per key                 | Transaction counts per time bucket     |
| `ReducingState` | Aggregates values as they arrive             | Running sum of amounts                 |

**Keyed State** is state that is automatically partitioned by the stream's key. In our case, each `customer_id` has its own independent state — Flink guarantees that all events with the same `customer_id` go to the same Flink task, so state access is always local (no distributed locks needed).

```
customer_id = "C001"  →  Task 1  →  State for C001 only
customer_id = "C002"  →  Task 2  →  State for C002 only
customer_id = "C003"  →  Task 1  →  State for C003 only
```

**State Backend** determines where state is stored:

- `HashMapStateBackend` (default): State lives in JVM heap memory. Fast, but limited by RAM. Good for development.
- `EmbeddedRocksDBStateBackend`: State lives in RocksDB (on-disk, with memory cache). Handles very large state. Best for production fraud detection where you track millions of customers.

```yaml
# flink-conf.yaml
state.backend: rocksdb
state.backend.rocksdb.memory.managed: true
```

**State TTL (Time-to-Live):** You don't want to track a customer's transactions forever — state would grow unboundedly. Set a TTL so old transaction history is automatically garbage-collected.

```python
# Keep transaction history for 1 hour, then auto-expire
ttl_config = StateTtlConfig \
    .new_builder(Time.hours(1)) \
    .set_update_type(StateTtlConfig.UpdateType.OnCreateAndWrite) \
    .set_state_visibility(StateTtlConfig.StateVisibility.NeverReturnExpired) \
    .build()
state_descriptor.enable_time_to_live(ttl_config)
```

---

## 4. Flink Configuration Deep Dive <a name="flink-configuration"></a>

See `config/flink-conf.yaml` for the full annotated configuration.

Key sections:
- **JobManager settings** — controls the master process
- **TaskManager settings** — controls the worker processes
- **Memory model** — how Flink partitions heap/off-heap/network memory
- **Checkpointing** — fault tolerance and recovery
- **State backend** — where keyed state is stored
- **Parallelism** — default level of parallel task execution

---

## 5. Project Setup <a name="project-setup"></a>

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | **3.11.x** | 3.12+ breaks apache-beam — use pyenv to manage |
| Java | **11** | Required by PyFlink's JVM bridge |
| Docker | any recent | Optional — only needed for cluster mode |

---

### Step 1 — Install Python 3.11 via pyenv

If you don't have pyenv yet:
```bash
brew install pyenv
echo 'eval "$(pyenv init -)"' >> ~/.zshrc
source ~/.zshrc
```

Install Python 3.11 and pin it to this project folder:
```bash
pyenv install 3.11.9
cd 07-Flink-Case            # your project folder
pyenv local 3.11.9          # creates .python-version file, affects this folder only

python --version            # should print: Python 3.11.9
```

> **Why 3.11?** PyFlink depends on `apache-beam`, which has no pre-built wheel
> for macOS arm64 on Python 3.12 and cannot compile from source on modern setuptools.
> Python 3.11 is the current standard for the data engineering ecosystem
> (PyFlink, PySpark, pandas all test against 3.11 first).

---

### Step 2 — Install Java 11

PyFlink's JVM bridge (`pemja`) requires Java 11 specifically:
```bash
brew install openjdk@11
export JAVA_HOME=$(brew --prefix openjdk@11)

# Add to your shell profile so it persists across sessions:
echo 'export JAVA_HOME=$(brew --prefix openjdk@11)' >> ~/.zshrc
source ~/.zshrc

java -version               # should print: openjdk version "11.x.x"
```

---

### Step 3 — Create a virtual environment

Always use a venv — never install into your system Python:
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Your prompt should now show: (.venv)
pip install --upgrade pip setuptools
```

---

### Step 4 — Install dependencies

> **Important:** PyFlink must be installed with `--no-deps` first.
> Its declared dependency on `apache-beam` cannot be built on macOS arm64.
> Our tutorial only uses the DataStream API — `apache-beam` is never needed.

```bash
# 1. Install PyFlink without pulling in apache-beam
pip install apache-flink==2.2.0 --no-deps

# 2. Install all other dependencies (all have pre-built wheels)
pip install -r requirements.txt

# 3. Confirm no critical conflicts
pip check
```

Expected output from `pip check`:
```
No broken requirements found.
```

---

### Step 5 — Verify the installation

```bash
python -c "
import pyflink, pandas, flask
from pyflink.datastream import StreamExecutionEnvironment
print('PyFlink: ', pyflink.__version__)
print('pandas:  ', pandas.__version__)
print('Flask:   ', flask.__version__)
print('All OK')
"
```

---

### Troubleshooting

**`ModuleNotFoundError: No module named 'pkg_resources'`**
You are installing into the system Python, not a venv. Make sure your prompt
shows `(.venv)` before running pip commands.

**`ERROR: Failed to build apache-beam`**
You ran `pip install -r requirements.txt` without first running
`pip install apache-flink==2.2.0 --no-deps`. The `--no-deps` step is required
to prevent pip from trying to build apache-beam from source.

**`pemja` or `pandas` version conflict warnings**
These are resolved by `requirements.txt` which pins exact compatible versions.
Run `pip install -r requirements.txt` again after the `--no-deps` install.

**Java not found at runtime**
Make sure `JAVA_HOME` is set: `echo $JAVA_HOME` should print a path.
If empty, run `export JAVA_HOME=$(brew --prefix openjdk@11)`.

---

### .gitignore

Add these to your `.gitignore` before pushing:
```
.venv/
.python-version
data/
__pycache__/
*.pyc
```

---

### Run locally (recommended for learning)

Open three separate terminal tabs, each with the venv activated:

```bash
# Terminal 1 — generates transactions.jsonl continuously
python src/data_generator.py

# Terminal 2 — reads transactions, writes alerts.jsonl
python src/fraud_detector.py

# Terminal 3 — serves the dashboard
python dashboard/server.py
```

Then open **http://localhost:8050** in your browser.

### Start the Flink cluster (optional, cluster mode only)
```bash
docker-compose up -d
# Flink Web UI available at http://localhost:8081
```

---

## 6. Data Generator <a name="data-generator"></a>

See `src/data_generator.py`. It generates realistic transactions including:
- Normal spending patterns (small amounts, regular hours)
- Injected fraud scenarios (velocity bursts, high-value anomalies, night transactions)
- Realistic event-time delays and out-of-order delivery

---

## 7. PyFlink Fraud Detection Pipeline <a name="pyflink-pipeline"></a>

See `src/fraud_detector.py`. The pipeline stages:

1. **Source**: Read from `transactions.jsonl` (written by data generator)
2. **Parse**: Deserialize JSON → transaction objects
3. **Watermark Assignment**: Extract `event_time` field, apply 5s bounded lateness
4. **KeyBy**: Partition stream by `customer_id`
5. **FraudDetectionFunction**: Stateful per-customer rule engine (Rules R1, R2, R4, R5)
6. **Window Aggregation**: Tumbling 10-min windows for Rule R3
7. **Union**: Merge all alert streams
8. **Sink**: Write to `alerts.jsonl` + dashboard file

---

## 8. Dashboard <a name="dashboard"></a>

See `dashboard/server.py` and `dashboard/index.html`.

Built with Flask + Chart.js. Polls `alerts.jsonl` every 2 seconds and shows:
- Transaction volume per minute (line chart)
- Fraud alert rate (line chart)
- Active alerts table (sortable by risk score)
- Fraud rule breakdown (bar chart)
- Simulated transaction map (scatter plot by region)

---

## 9. Exercises <a name="exercises"></a>

**Beginner:**
1. Modify Rule R1's threshold from $10,000 to $5,000. How does the alert rate change?
2. Change the watermark lateness from 5 seconds to 30 seconds. Observe the effect on window firing.

**Intermediate:**
3. Add a new Rule R6: flag any customer who transacts in more than 3 different "cities" within 30 minutes.
4. Change the state backend from HashMapStateBackend to EmbeddedRocksDBStateBackend and observe the configuration changes needed.

**Advanced:**
5. Add a Kafka source (replace the file source) and run in cluster mode using docker-compose.
6. Implement a "cooling-off" period: once a customer is flagged, suppress further alerts for 5 minutes using state TTL.
