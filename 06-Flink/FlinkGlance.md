# Apache Flink Tutorial: Getting Started with Docker

## 1. What is Apache Flink?

Apache Flink is an open-source distributed stream processing framework designed for stateful computations over unbounded and bounded data streams. It excels at real-time data processing with exactly-once semantics, event-time processing, and fault tolerance.

**Key capabilities:**

- Real-time stream processing
- Batch processing (bounded streams)
- Event-time windowing
- Stateful computations with checkpointing
- Exactly-once delivery guarantees

---

## 2. Prerequisites

- Docker and Docker Compose installed on your machine
- A web browser to access the Flink Web UI
- Basic familiarity with command-line tools

---

## 3. Install Flink Using Docker Compose

### Step 1: Create the project directory

```bash
mkdir flink-demo && cd flink-demo
```

### Step 2: Create `docker-compose.yml`

```yaml
version: "3.8"

services:
  jobmanager:
    image: flink:1.18-java11
    container_name: flink-jobmanager
    ports:
      - "8081:8081"       # Flink Web UI
    command: jobmanager
    environment:
      FLINK_PROPERTIES: |
        jobmanager.rpc.address: jobmanager
        state.backend: hashmap
        state.checkpoints.dir: file:///tmp/flink-checkpoints
        heartbeat.interval: 1000
        heartbeat.timeout: 5000

  taskmanager:
    image: flink:1.18-java11
    container_name: flink-taskmanager
    depends_on:
      - jobmanager
    command: taskmanager
    environment:
      FLINK_PROPERTIES: |
        jobmanager.rpc.address: jobmanager
        taskmanager.numberOfTaskSlots: 4
        state.backend: hashmap
        state.checkpoints.dir: file:///tmp/flink-checkpoints
        heartbeat.interval: 1000
        heartbeat.timeout: 5000
    scale: 1  # Change to 2 or more for multiple TaskManagers
```

### Step 3: Start the cluster

```bash
docker compose up -d
```

### Step 4: Verify

```bash
docker compose ps
```

You should see both `flink-jobmanager` and `flink-taskmanager` running.

---

## 4. Access the Flink Web UI

Open your browser and navigate to:

```
http://localhost:8081
```

### What You'll See — The Dashboard

The Flink Web UI is your central control panel. Here's a tour of the main sections:

| Section | Description |
|---------|-------------|
| **Overview** | Cluster summary: running/finished/cancelled/failed jobs, available task slots, and TaskManagers |
| **Running Jobs** | List of currently executing jobs with start time, duration, and status |
| **Completed Jobs** | History of finished, cancelled, and failed jobs |
| **Task Managers** | Connected worker nodes, their slots, CPU, memory, and data port info |
| **Job Manager** | Configuration details, log files, and stdout of the JobManager process |
| **Submit New Job** | Upload and submit a JAR file to run a Flink job |

---

## 5. Flink Architecture at a Glance

```
┌─────────────────────────────────────────────┐
│               Flink Cluster                 │
│                                             │
│   ┌──────────────┐    ┌──────────────────┐  │
│   │ JobManager   │───▶│ TaskManager (1)  │  │
│   │              │    │  Slot 1 │ Slot 2 │  │
│   │  • Scheduling│    │  Slot 3 │ Slot 4 │  │
│   │  • Checkpoint│    └──────────────────┘  │
│   │  • Recovery  │    ┌──────────────────┐  │
│   │  • Web UI    │───▶│ TaskManager (2)  │  │
│   └──────────────┘    │  (if scaled)     │  │
│                       └──────────────────┘  │
└─────────────────────────────────────────────┘
```

- **JobManager**: The coordinator — schedules tasks, triggers checkpoints, manages recovery.
- **TaskManager**: The workers — execute the actual data processing tasks in parallel slots.

---

## 6. Run a Built-in Example Job

Flink ships with example JARs. Let's run the classic **WordCount** example.

### Option A: Submit via command line

```bash
# Enter the JobManager container
docker exec -it flink-jobmanager bash

# Run the WordCount example
flink run /opt/flink/examples/streaming/WordCount.jar

# Exit the container
exit
```

### Option B: Submit via the Web UI

1. Go to **http://localhost:8081**
2. Click **"Submit New Job"** in the left sidebar
3. Click **"+ Add New"** and upload the JAR file:
   - Path inside container: `/opt/flink/examples/streaming/WordCount.jar`
   - (Copy it out first: `docker cp flink-jobmanager:/opt/flink/examples/streaming/WordCount.jar .`)
4. Select the uploaded JAR → click **"Submit"**

### Observe the results

After submission, navigate to **Running Jobs** (or **Completed Jobs** once it finishes). Click on the job to see:

- **Job Graph**: Visual DAG of operators (Source → FlatMap → KeyBy/Sum → Sink)
- **Timeline**: Execution timeline across TaskManager slots
- **Checkpoints**: Checkpoint history, size, and duration
- **Exceptions**: Any errors that occurred
- **Configuration**: Runtime parameters for this job

---

## 7. Explore the Web UI in Detail

### 7.1 Job Graph View

When you click into a job, the **Job Graph** tab shows the execution plan as a directed acyclic graph (DAG). Each box represents an operator:

- **Source**: Reads input data
- **Transformation**: Operations like `map`, `flatMap`, `keyBy`, `window`
- **Sink**: Writes output data

Click any operator to see: parallelism, bytes sent/received, records in/out, and back pressure status.

### 7.2 Task Managers View

Navigate to **Task Managers** to see:

- **Free Slots / Total Slots**: How much capacity is available
- **CPU Cores / Physical Memory / JVM Heap**: Resource allocation
- **Logs & Stdout**: Debugging output from each worker

### 7.3 Checkpoints Tab (inside a running job)

Flink's fault tolerance relies on checkpoints. The Checkpoints tab shows:

- **Checkpoint Count**: How many completed
- **Latest Checkpoint Size**: State snapshot size
- **End-to-End Duration**: Time to complete the checkpoint
- **Alignment Duration**: Time waiting for barrier alignment

### 7.4 Metrics

Flink exposes extensive metrics. In the Job Graph view, select an operator and check the **Metrics** tab for:

- `numRecordsIn` / `numRecordsOut`
- `numBytesIn` / `numBytesOut`
- `currentInputWatermark`
- `checkpointAlignmentTime`

---

## 8. Run a Custom Python Job (PyFlink)

For a more hands-on experience, let's create a simple PyFlink job.

### Step 1: Create the Python script

Create a file called `word_count.py`:

```python
from pyflink.table import EnvironmentSettings, TableEnvironment

# Create a batch TableEnvironment
env_settings = EnvironmentSettings.in_batch_mode()
t_env = TableEnvironment.create(env_settings)

# Define source data
source_ddl = """
    CREATE TABLE source_table (
        word STRING
    ) WITH (
        'connector' = 'filesystem',
        'path' = '/tmp/input.txt',
        'format' = 'raw'
    )
"""

# Define sink
sink_ddl = """
    CREATE TABLE sink_table (
        word STRING,
        cnt BIGINT
    ) WITH (
        'connector' = 'print'
    )
"""

t_env.execute_sql(source_ddl)
t_env.execute_sql(sink_ddl)

# Run word count query
t_env.execute_sql("""
    INSERT INTO sink_table
    SELECT word, COUNT(*) AS cnt
    FROM source_table
    GROUP BY word
""").wait()

print("Word count job completed!")
```

### Step 2: Run it

```bash
# Copy the script into the container
docker cp word_count.py flink-jobmanager:/tmp/

# Create sample input
docker exec -it flink-jobmanager bash -c \
  'echo -e "hello\nworld\nhello\nflink\nflink\nflink" > /tmp/input.txt'

# Run with PyFlink (if available in the image)
docker exec -it flink-jobmanager bash -c \
  'cd /opt/flink && python /tmp/word_count.py'
```

> **Note:** The default Flink Docker image may not include PyFlink. For PyFlink support, use the image `apache/flink:1.18-java11` or build a custom image with `pip install apache-flink`.

---

## 9. Key Flink Concepts Summary

| Concept | Description |
|---------|-------------|
| **DataStream API** | Core API for processing unbounded (streaming) and bounded (batch) data |
| **Table API / SQL** | High-level relational API for declarative data processing |
| **Windowing** | Group events by time (tumbling, sliding, session windows) |
| **State** | Managed, fault-tolerant state for stateful operators |
| **Checkpointing** | Periodic snapshots of state for exactly-once recovery |
| **Watermarks** | Mechanism to handle late-arriving and out-of-order events |
| **Savepoints** | Manual snapshots for upgrades, migrations, and A/B testing |
| **Event Time** | Processing based on when events actually occurred, not when received |

---

## 10. Useful Commands Reference

```bash
# Start the cluster
docker compose up -d

# Stop the cluster
docker compose down

# View logs
docker compose logs -f jobmanager
docker compose logs -f taskmanager

# Scale TaskManagers (e.g., to 3 workers)
docker compose up -d --scale taskmanager=3

# Enter the JobManager shell
docker exec -it flink-jobmanager bash

# List running jobs
docker exec -it flink-jobmanager flink list

# Cancel a job
docker exec -it flink-jobmanager flink cancel <job-id>

# Trigger a savepoint
docker exec -it flink-jobmanager flink savepoint <job-id> /tmp/savepoints
```

---

## 11. Clean Up

```bash
docker compose down -v
rm -rf flink-demo
```

---

## Summary

In this tutorial you have:

1. **Deployed** a Flink cluster using Docker Compose (JobManager + TaskManager)
2. **Accessed** the Flink Web UI at `localhost:8081`
3. **Explored** the dashboard sections: Overview, Jobs, Task Managers, Job Manager
4. **Submitted** a built-in WordCount example job
5. **Observed** the Job Graph (DAG), checkpoints, metrics, and execution timeline
6. **Learned** key Flink concepts: streaming, state, checkpointing, and windowing

Flink's Web UI provides real-time visibility into your cluster's health and job execution, making it an essential tool for monitoring and debugging stream processing pipelines.
