
# Week 3 Tutorial: Kafka + JSON Schema

## Learning goal
Producers register schemas, messages carry schema IDs,
and consumers safely deserialize data using the same schema.  

This tutorial extends the Week 2 Kafka pipeline by adding **JSON Schema** using Confluent Schema Registry.  

## Files
- docker-compose.yml – Kafka (KRaft), Schema Registry, Kafka UI  
- requirements.txt  
- producer.py – JSON Schema–aware producer
- consumer.py – JSON Schema–aware consumer  
- schemas/person_event.schema.json – message schema  

## Steps  
1.Launch Docker desktop on your computer    

2. Remove the old container from last week   
- Click the "remove" icon on Docker  
- run this command in the project folder last time  
  `docker compose down`  
  
3. Create a new project folder in your local drive e.g.'week3'  
   
4. copy all the files in this folder to your local folder)  
   
5. Open Terminal 1, and change directory to your project folder e.g., 'week3'  

6. Start Kafka and Schema Registry:  
   `docker compose up -d`  

7. Install Python dependency:  
   This installs all required packages.  
   `python -m pip install -r requirements.txt`  

8. Run consumer (Terminal 1):  
   `python consumer.py`

9. Run producer (Terminal 2):  
   `python producer.py`  

Check if the data from producer can be read on consumer Terminal.


