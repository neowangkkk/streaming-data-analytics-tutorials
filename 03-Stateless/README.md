# Stateless Fraud Detection (Excel -> Kafka -> Stateless Processor)

This tutorial demonstrates stateless streaming with `confluent-kafka` using an Excel file as the input data source.

## What you will build

Input:
- Excel file: `payments_input.xlsx` (sheet `payments`)
- Kafka topic: `payments.raw`

Stateless processing:
- Read one event at a time
- Compute `risk_score` + `risk_reasons` (rule-based, stateless)
- Route to:
  - `payments.flagged` (risk_score >= 60)
  - `payments.approved` (otherwise)
- Bad messages go to `payments.dlq`

Tracing:
- The producer attaches `excel_row` as a Kafka header
- The processor propagates `excel_row` to output topics

## Requirements

- Docker + Docker Compose
- Python 3.10+
- pip packages:
  - confluent-kafka
  - confluent-kafka[json]
  - openpyxl

Install:
```bash
pip install confluent-kafka 'confluent-kafka[json]' openpyxl
```

## 1) Start Kafka + Schema Registry

```bash
docker compose up -d
```

## 2) Create topics

```bash
bash topic_setup.sh
```

## 3) Produce events from Excel

```bash
python producer_payments_from_excel.py
```

## 4) Run the stateless fraud detector (in another terminal)

```bash
python stateless_fraud_detector.py
```

## 5) Read results

In separate terminals:
```bash
python read_with_headers.py payments.approved
python read_with_headers.py payments.flagged
python read_topic.py payments.dlq
```

## Scale the stateless processor

Run multiple instances of the detector (same group.id). Kafka will split partitions across them:
```bash
python stateless_fraud_detector.py
python stateless_fraud_detector.py
```

## Next tutorial (stateful)

To move to stateful fraud detection, you will add history-dependent rules:
- velocity per card (N transactions in last X minutes)
- rolling sum(amount) windows
- last-seen country per card (sudden jumps)
