# Kafka + ksqlDB (Docker Compose) Tutorial
This folder runs **Kafka (KRaft mode)** and **ksqlDB** using Docker Compose, then uses a **Producer Terminal** to send **five sample JSON messages** to a Kafka topic and reads them in ksqlDB.

Works on macOS (Intel or Apple Silicon), Windows, and Linux with Docker Desktop (or Docker Engine).

---

## What you will run
- **Kafka broker** in a container
- **ksqlDB Server** in a container
- **ksqlDB CLI** in a container (interactive terminal)

You will use:
- One terminal for Docker commands
- One terminal as **Producer Terminal**
- One terminal for **ksqlDB CLI**

---

## 0) Prerequisites
Install:
- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
- Docker Compose v2 (included in Docker Desktop)

Check:
```bash
docker --version
docker compose version
```

---

## 1) Clean start (important if you saw errors)
If you previously saw either of these:
- `Invalid cluster.id in /var/lib/kafka/data/meta.properties`
- `CLUSTER_ID is required`
- Port error: `bind: address already in use` for `9092`

Do a clean reset in THIS folder:

```bash
docker compose down -v --remove-orphans
```

This removes the Kafka data volume so Kafka can initialize correctly next time.

If you also want to remove downloaded images (optional):
```bash
docker image prune -f
```

---

## 2) Docker Compose file 
Create a project folder in your computer e.g., "04-ksqlDB", and copy the files from this repo to your project folder.  

This tutorial expects a `docker-compose.yml` in your folder.

Notes:
- Uses a named volume `kafka_data` (safe persistence, easy reset with `down -v`)
- Sets **two listeners**:
  - `kafka:29092` (inside Docker network, used by ksqlDB and docker exec commands)
  - `localhost:9092` (your host machine, optional for host-based tools)
- Pre-generates a stable `CLUSTER_ID` so KRaft can format storage reliably.  


### Apple Silicon (M1/M2/M3) note
Docker may warn about platform mismatch for some images. If you want to force amd64 explicitly, add this under each service:

```yaml
platform: linux/amd64
```

This is optional, but can reduce confusion in class.

---

## 3) Start everything
From this folder:

```bash
docker compose up -d
```

Check status:
```bash
docker compose ps
```

Expected: `kafka` and `ksqldb-server` should be running. `ksqldb-cli` may show as “running” or “exited” depending on your Docker UI; that is ok because it is meant to be launched interactively.

---

## 4) If you get “port 9092 already in use”
On macOS/Linux, check who is using it:

```bash
lsof -nP -iTCP:9092 -sTCP:LISTEN
```

If it’s a Java process and you do NOT need it, you can stop it:

```bash
kill <PID>
```

If you are unsure, do not kill it; instead, change the host port in compose from `9092:9092` to `19092:9092` and use `localhost:19092` from your host tools.

---

## 5) Create the `users` topic
Run this from your normal terminal:

```bash
docker compose exec kafka kafka-topics \
  --bootstrap-server kafka:29092 \
  --create \
  --topic users \
  --partitions 4 \
  --replication-factor 1
```

Verify:
```bash
docker compose exec kafka kafka-topics --bootstrap-server kafka:29092 --list
docker compose exec kafka kafka-topics --bootstrap-server kafka:29092 --describe --topic users
```

---

## 6) Open ksqlDB CLI (ksql> terminal)
In a new terminal:

```bash
docker compose exec ksqldb-cli ksql http://ksqldb-server:8088
```

You should see a `ksql>` prompt.

Inside ksqlDB, confirm the Kafka topic exists:

```sql
SHOW TOPICS;
```

---

## 7) Create a stream on top of the `users` topic
In the `ksql>` terminal:

```sql
CREATE STREAM users_stream (
  user_id VARCHAR KEY,
  name VARCHAR,
  age INT
) WITH (
  KAFKA_TOPIC='users',
  VALUE_FORMAT='JSON'
);
```

Check:
```sql
SHOW STREAMS;
DESCRIBE users_stream;
```

---

## 8) Producer Terminal: produce five sample messages
Open another terminal window called **Producer Terminal**.

Run:

```bash
docker compose exec kafka kafka-console-producer \
  --bootstrap-server kafka:29092 \
  --topic users
```

Now paste these **five lines** (each line is one message):

```json
{"user_id":"u1","name":"Alice","age":16}
{"user_id":"u2","name":"Ben","age":17}
{"user_id":"u3","name":"Chen","age":16}
{"user_id":"u4","name":"Dina","age":18}
{"user_id":"u5","name":"Evan","age":17}
```

Stop the producer with `Ctrl+C`.

---

## 9) Read the messages in ksqlDB
Back in the `ksql>` terminal:

```sql
SELECT * FROM users_stream EMIT CHANGES;
```

You should see the five rows appear.

Stop the live query with `Ctrl+C`.

---

## 10) Example transformation: keep only users age 17+
In `ksql>`:

```sql
CREATE STREAM users_older AS
SELECT user_id, name, age
FROM users_stream
WHERE age >= 17
EMIT CHANGES;
```

Read:
```sql
SELECT * FROM users_older EMIT CHANGES;
```

Stop with `Ctrl+C`.

Show topics again (ksqlDB may create internal topics too):
```sql
SHOW TOPICS;
```

---

## 11) Optional: raw Kafka consumer (no SQL)
Open another terminal (Consumer Terminal):

```bash
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server kafka:29092 \
  --topic users \
  --from-beginning
```

Stop with `Ctrl+C`.

---

## 12) Stop everything
```bash
docker compose down
```

### Full reset (removes Kafka data too)
```bash
docker compose down -v --remove-orphans
```

---

## Troubleshooting

### A) `service "kafka" is not running`
Kafka container crashed. Check logs:

```bash
docker compose logs kafka --tail 200
```

Common cause: KRaft metadata mismatch from old data. Fix with:

```bash
docker compose down -v --remove-orphans
docker compose up -d
```

### B) `Invalid cluster.id in meta.properties`
Same fix: you have old Kafka data from a different cluster id.

```bash
docker compose down -v --remove-orphans
docker compose up -d
```

### C) ksqlDB CLI shows repeated RMI/JMX “Accept timed out” warnings
These warnings are annoying but usually harmless. They come from Java management (JMX) inside the CLI container.

If you want to reduce noise, you can run the CLI like this (one-off command):

```bash
docker compose run --rm -e JMX_PORT= -e JAVA_TOOL_OPTIONS="-Dcom.sun.management.jmxremote=false" \
  ksqldb-cli ksql http://ksqldb-server:8088
```

(We do not bake this into the service because different Java builds handle flags differently.)

### D) Windows notes
- Use **PowerShell** or **Windows Terminal**.
- Prefer `docker compose` (space) instead of `docker-compose`.
- Copy/paste JSON lines carefully (each line is one message).

---

## What you should remember (plain language)
- Kafka is like a **mailroom** with many **mailboxes** (topics).
- Producers **drop messages** into a mailbox.
- Consumers **read messages** from a mailbox.
- ksqlDB lets you **treat a topic like a table**, and write SQL to filter/transform streams.
- Docker runs each piece (Kafka, ksqlDB) in its own **container**, which is like a small isolated computer.
