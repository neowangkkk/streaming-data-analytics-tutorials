#!/usr/bin/env python3
"""
IoT Sensor Simulator
Generates simulated sensor data and sends to Kafka
"""

import json
import time
import random
from datetime import datetime
from confluent_kafka import Producer
import sys

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'
TOPIC_NAME = 'iot-sensors'

# Sensor locations (matching user cities for easier joining)
SENSORS = [
    {'sensor_id': 'SENSOR_001', 'location': 'Toronto', 'latitude': 43.6532, 'longitude': -79.3832},
    {'sensor_id': 'SENSOR_002', 'location': 'New York', 'latitude': 40.7128, 'longitude': -74.0060},
    {'sensor_id': 'SENSOR_003', 'location': 'San Francisco', 'latitude': 37.7749, 'longitude': -122.4194},
    {'sensor_id': 'SENSOR_004', 'location': 'London', 'latitude': 51.5074, 'longitude': -0.1278},
    {'sensor_id': 'SENSOR_005', 'location': 'Tokyo', 'latitude': 35.6895, 'longitude': 139.6917},
]

def delivery_callback(err, msg):
    """Callback for message delivery reports"""
    if err:
        print(f'ERROR: Message delivery failed: {err}', file=sys.stderr)
    else:
        print(f'✓ Produced to {msg.topic()} [{msg.partition()}] @ offset {msg.offset()}')

def generate_sensor_reading(sensor):
    """Generate a realistic sensor reading"""
    # Base temperature varies by location (rough approximation)
    base_temps = {
        'Toronto': 15,
        'New York': 18,
        'San Francisco': 16,
        'London': 12,
        'Tokyo': 17
    }
    
    base_temp = base_temps.get(sensor['location'], 15)
    
    reading = {
        'sensor_id': sensor['sensor_id'],
        'location': sensor['location'],
        'latitude': sensor['latitude'],
        'longitude': sensor['longitude'],
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'temperature_celsius': round(base_temp + random.uniform(-5, 10), 2),
        'humidity_percent': round(random.uniform(30, 80), 2),
        'pressure_hpa': round(random.uniform(980, 1030), 2),
        'air_quality_index': random.randint(0, 200)
    }
    
    return reading

def main():
    print("=== IoT Sensor Simulator ===")
    print(f"Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    print(f"Topic: {TOPIC_NAME}")
    print(f"Sensors: {len(SENSORS)}")
    print("\nStarting data generation...\n")
    
    # Configure Kafka producer
    conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'client.id': 'iot-sensor-simulator'
    }
    
    producer = Producer(conf)
    
    try:
        while True:
            # Generate reading for each sensor
            for sensor in SENSORS:
                reading = generate_sensor_reading(sensor)
                
                # Serialize to JSON
                message_value = json.dumps(reading)
                
                # Produce to Kafka
                producer.produce(
                    topic=TOPIC_NAME,
                    key=sensor['sensor_id'],
                    value=message_value,
                    callback=delivery_callback
                )
            
            # Flush to ensure delivery
            producer.flush()
            
            # Wait before next batch
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        # Wait for any outstanding messages to be delivered
        producer.flush()
        print("Shutdown complete.")

if __name__ == '__main__':
    main()
