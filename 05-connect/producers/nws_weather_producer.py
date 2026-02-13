#!/usr/bin/env python3
"""
NWS Weather.gov API Producer
Fetches official US weather data from National Weather Service API
"""

import json
import time
import requests
from datetime import datetime
from confluent_kafka import Producer
import sys

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'
TOPIC_NAME = 'weather-data'

# US Cities (matching IoT sensors and database)
CITIES = [
    {'name': 'New York', 'state': 'NY', 'lat': 40.7128, 'lon': -74.0060},
    {'name': 'Los Angeles', 'state': 'CA', 'lat': 34.0522, 'lon': -118.2437},
    {'name': 'Chicago', 'state': 'IL', 'lat': 41.8781, 'lon': -87.6298},
    {'name': 'San Francisco', 'state': 'CA', 'lat': 37.7749, 'lon': -122.4194},
    {'name': 'Miami', 'state': 'FL', 'lat': 25.7617, 'lon': -80.1918},
]

def delivery_callback(err, msg):
    """Kafka delivery callback"""
    if err:
        print(f'✗ ERROR: {err}', file=sys.stderr)
    else:
        print(f'✓ {msg.key().decode()}: {msg.topic()} [{msg.partition()}] @ {msg.offset()}')

def get_forecast_url(lat, lon):
    """Get forecast URL from NWS points endpoint"""
    url = f"https://api.weather.gov/points/{lat},{lon}"
    headers = {
        'User-Agent': 'KafkaStreamingTutorial/1.0 (education@example.com)',
        'Accept': 'application/geo+json'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data['properties']['forecast']
    except Exception as e:
        print(f"Error getting forecast URL for {lat},{lon}: {e}", file=sys.stderr)
        return None

def fetch_weather(city):
    """Fetch weather forecast from NWS API"""
    # Get forecast URL
    forecast_url = get_forecast_url(city['lat'], city['lon'])
    if not forecast_url:
        return None
    
    headers = {
        'User-Agent': 'KafkaStreamingTutorial/1.0 (education@example.com)',
        'Accept': 'application/geo+json'
    }
    
    try:
        response = requests.get(forecast_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Extract current period (first forecast period)
        if data.get('properties', {}).get('periods'):
            current = data['properties']['periods'][0]
            
            # Convert Fahrenheit to Celsius
            temp_f = current.get('temperature', 0)
            temp_c = round((temp_f - 32) * 5/9, 2)
            
            weather_data = {
                'city': city['name'],
                'state': city['state'],
                'latitude': city['lat'],
                'longitude': city['lon'],
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'temperature_f': temp_f,
                'temperature_c': temp_c,
                'temperature_unit': current.get('temperatureUnit', 'F'),
                'wind_speed': current.get('windSpeed', 'N/A'),
                'wind_direction': current.get('windDirection', 'N/A'),
                'short_forecast': current.get('shortForecast', 'N/A'),
                'detailed_forecast': current.get('detailedForecast', ''),
                'is_daytime': current.get('isDaytime', True),
                'period_name': current.get('name', 'Current'),
                'icon': current.get('icon', '')
            }
            
            return weather_data
        
        return None
        
    except Exception as e:
        print(f"Error fetching weather for {city['name']}: {e}", file=sys.stderr)
        return None

def main():
    print("=" * 60)
    print("  NWS Weather.gov API Producer")
    print("=" * 60)
    print(f"Kafka:  {KAFKA_BOOTSTRAP_SERVERS}")
    print(f"Topic:  {TOPIC_NAME}")
    print(f"API:    api.weather.gov (Official US National Weather Service)")
    print(f"Cities: {len(CITIES)}")
    print()
    print("Fetching weather every 60 seconds...")
    print("(NWS updates hourly)")
    print("=" * 60)
    print()
    
    # Configure Kafka producer
    conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'client.id': 'nws-weather-producer'
    }
    
    producer = Producer(conf)
    
    try:
        iteration = 0
        while True:
            iteration += 1
            print(f"\n[Fetch #{iteration}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("-" * 60)
            
            for city in CITIES:
                weather = fetch_weather(city)
                
                if weather:
                    # Produce to Kafka
                    producer.produce(
                        topic=TOPIC_NAME,
                        key=city['name'],
                        value=json.dumps(weather),
                        callback=delivery_callback
                    )
                    
                    # Print summary
                    print(f"  {city['name']:15s} | {weather['temperature_f']:3.0f}°F ({weather['temperature_c']:4.1f}°C) | {weather['short_forecast']}")
                else:
                    print(f"  {city['name']:15s} | ✗ Failed to fetch")
            
            # Flush messages
            producer.flush()
            
            print("-" * 60)
            print(f"Next update in 60 seconds...\n")
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("  Shutting down NWS Weather Producer...")
        print("=" * 60)
    finally:
        producer.flush()
        print("Complete.\n")

if __name__ == '__main__':
    main()
