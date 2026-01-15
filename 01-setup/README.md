# Kafka quickstart using Docker Compose


### Setup: Run Kafka Locally with Docker Compose

In this tutorial you will start Kafka locally using Docker Compose, then verify the broker is running.

## Prerequisite
Docker Desktop must be installed and running.


### 1. Go to your tutorial project folder
Start Kafka (and any other services in the compose file):

<<<docker compose up -d<<<

Confirm containers are running:

docker compose ps  


### 2) Install Python package: confluent-kafka

Create and activate a Python virtual environment (recommended):

python3 -m venv .venv
source .venv/bin/activate


Install the package:

pip install --upgrade pip
pip install confluent-kafka

  
### 3) Create producer and consumer files (instructions only)

In this 01-setup folder, create two files:

producer.py

consumer.py

Copy the code provided in the next tutorial section (or from the course materials) into these files.

Make sure both files use the correct broker address, usually:

localhost:9092

   
### 4) Run the Python files in two terminals   
  
#### Open Terminal A

Go to your project folder and activate your environment:
source .venv/bin/activate  

Start the consumer:

python consumer.py


  
#### Terminal B (Producer)

Go to your project folder and activate your environment:
source .venv/bin/activate

Run the producer:

python producer.py


Stop the consumer with Ctrl + C.
