-- Users table for environmental monitoring system
-- Cities match weather API and IoT sensors for easy joining

CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    city VARCHAR(50) NOT NULL,
    state VARCHAR(2) NOT NULL,
    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert users across the 5 cities
-- NEW YORK
INSERT INTO users (username, email, city, state, latitude, longitude) VALUES
('alice_smith', 'alice@example.com', 'New York', 'NY', 40.712800, -74.006000),
('bob_johnson', 'bob@example.com', 'New York', 'NY', 40.758900, -73.985100),
('charlie_brown', 'charlie@example.com', 'New York', 'NY', 40.730600, -73.935200);

-- LOS ANGELES
INSERT INTO users (username, email, city, state, latitude, longitude) VALUES
('diana_garcia', 'diana@example.com', 'Los Angeles', 'CA', 34.052200, -118.243700),
('erik_martinez', 'erik@example.com', 'Los Angeles', 'CA', 34.098900, -118.327200),
('fiona_lopez', 'fiona@example.com', 'Los Angeles', 'CA', 34.016700, -118.493900);

-- CHICAGO
INSERT INTO users (username, email, city, state, latitude, longitude) VALUES
('george_wilson', 'george@example.com', 'Chicago', 'IL', 41.878100, -87.629800),
('hannah_davis', 'hannah@example.com', 'Chicago', 'IL', 41.891700, -87.626700),
('ian_rodriguez', 'ian@example.com', 'Chicago', 'IL', 41.836900, -87.684500);

-- SAN FRANCISCO
INSERT INTO users (username, email, city, state, latitude, longitude) VALUES
('julia_lee', 'julia@example.com', 'San Francisco', 'CA', 37.774900, -122.419400),
('kevin_kim', 'kevin@example.com', 'San Francisco', 'CA', 37.795900, -122.393900),
('laura_chen', 'laura@example.com', 'San Francisco', 'CA', 37.729000, -122.475800);

-- MIAMI
INSERT INTO users (username, email, city, state, latitude, longitude) VALUES
('mike_anderson', 'mike@example.com', 'Miami', 'FL', 25.761700, -80.191800),
('nancy_thomas', 'nancy@example.com', 'Miami', 'FL', 25.790700, -80.130100),
('oscar_white', 'oscar@example.com', 'Miami', 'FL', 25.728600, -80.237400);

-- Create indexes for faster lookups
CREATE INDEX idx_users_id ON users(user_id);
CREATE INDEX idx_users_city ON users(city);
CREATE INDEX idx_users_state ON users(state);

-- Verify data
SELECT 
    city, 
    state,
    COUNT(*) as user_count 
FROM users 
GROUP BY city, state 
ORDER BY city;

SELECT COUNT(*) as total_users FROM users;
