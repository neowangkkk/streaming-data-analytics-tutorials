#!/usr/bin/env python3
"""
IoT Sensor Simulator
Generates environmental sensor data for US cities (matching weather & database)
"""

import json
import time
import random
from datetime import datetime
from confluent_kafka import Producer
import sys

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'
TOPIC_NAME = 'iot-sensors'

# IoT Sensors (matching weather API and database)
SENSORS = [
    {
        'sensor_id': 'SENSOR_NY_001',
        'location': 'New York',
        'state': 'NY',
        'latitude': 40.7128,
        'longitude': -74.0060,
        'base_temp': 55,  # Base temperature for variation
        'base_humidity': 65,
        'base_pressure': 1013,
        'base_aqi': 45
    },
    {
        'sensor_id': 'SENSOR_LA_001',
        'location': 'Los Angeles',
        'state': 'CA',
        'latitude': 34.0522,
        'longitude': -118.2437,
        'base_temp': 72,
        'base_humidity': 55,
        'base_pressure': 1015,
        'base_aqi': 85
    },
    {
        'sensor_id': 'SENSOR_CHI_001',
        'location': 'Chicago',
        'state': 'IL',
        'latitude': 41.8781,
        'longitude': -87.6298,
        'base_temp': 48,
        'base_humidity': 70,
        'base_pressure': 1012,
        'base_aqi': 50
    },
    {
        'sensor_id': 'SENSOR_SF_001',
        'location': 'San Francisco',
        'state': 'CA',
        'latitude': 37.7749,
        'longitude': -122.4194,
        'base_temp': 62,
        'base_humidity': 75,
        'base_pressure': 1014,
        'base_aqi': 40
    },
    {
        'sensor_id': 'SENSOR_MIA_001',
        'location': 'Miami',
        'state': 'FL',
        'latitude': 25.7617,
        'longitude': -80.1918,
        'base_temp': 78,
        'base_humidity': 80,
        'base_pressure': 1016,
        'base_aqi': 55
    }
]

def delivery_callback(err, msg):
    """Kafka delivery callback"""
    if err:
        print(f'✗ ERROR: {err}', file=sys.stderr)
    else:
        key = msg.key().decode() if msg.key() else 'unknown'
        print(f'✓ {key}: {msg.topic()} [{msg.partition()}] @ {msg.offset()}')

def generate_reading(sensor):
    """Generate realistic sensor reading with variations"""
    
    # Add realistic variations
    temp_variation = random.uniform(-5, 5)
    humidity_variation = random.uniform(-10, 10)
    pressure_variation = random.uniform(-3, 3)
    aqi_variation = random.randint(-15, 15)
    
    temperature_c = round(sensor['base_temp'] + temp_variation, 2)
    temperature_f = round((temperature_c * 9/5) + 32, 2)
    humidity = max(0, min(100, round(sensor['base_humidity'] + humidity_variation, 1)))
    pressure = round(sensor['base_pressure'] + pressure_variation, 2)
    aqi = max(0, min(500, sensor['base_aqi'] + aqi_variation))
    
    # Determine air quality status
    if aqi <= 50:
        aqi_status = 'Good'
    elif aqi <= 100:
        aqi_status = 'Moderate'
    elif aqi <= 150:
        aqi_status = 'Unhealthy for Sensitive Groups'
    elif aqi <= 200:
        aqi_status = 'Unhealthy'
    elif aqi <= 300:
        aqi_status = 'Very Unhealthy'
    else:
        aqi_status = 'Hazardous'
    
    reading = {
        'sensor_id': sensor['sensor_id'],
        'location': sensor['location'],
        'state': sensor['state'],
        'latitude': sensor['latitude'],
        'longitude': sensor['longitude'],
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'temperature_celsius': temperature_c,
        'temperature_fahrenheit': temperature_f,
        'humidity_percent': humidity,
        'pressure_hpa': pressure,
        'air_quality_index': aqi,
        'air_quality_status': aqi_status
    }
    
    return reading

def main():
    print("=" * 60)
    print("  IoT Environmental Sensor Simulator")
    print("=" * 60)
    print(f"Kafka:   {KAFKA_BOOTSTRAP_SERVERS}")
    print(f"Topic:   {TOPIC_NAME}")
    print(f"Sensors: {len(SENSORS)}")
    print()
    print("Generating sensor data every 5 seconds...")
    print("=" * 60)
    print()
    
    # Configure Kafka producer
    conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'client.id': 'iot-sensor-simulator'
    }
    
    producer = Producer(conf)
    
    try:
        iteration = 0
        while True:
            iteration += 1
            print(f"\n[Reading #{iteration}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("-" * 60)
            
            for sensor in SENSORS:
                reading = generate_reading(sensor)
                
                # Produce to Kafka
                producer.produce(
                    topic=TOPIC_NAME,
                    key=sensor['sensor_id'],
                    value=json.dumps(reading),
                    callback=delivery_callback
                )
                
                # Print summary
                print(f"  {reading['location']:15s} | "
                      f"{reading['temperature_fahrenheit']:5.1f}°F | "
                      f"{reading['humidity_percent']:4.1f}% | "
                      f"AQI: {reading['air_quality_index']:3d} ({reading['air_quality_status']})")
            
            # Flush messages
            producer.flush()
            
            print("-" * 60)
            print(f"Next reading in 5 seconds...\n")
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("  Shutting down IoT Sensor Simulator...")
        print("=" * 60)
    finally:
        producer.flush()
        print("Complete.\n")

if __name__ == '__main__':
    main()
