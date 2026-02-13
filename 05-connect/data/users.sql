-- Create users table
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    city VARCHAR(50) NOT NULL,
    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample users in different cities
INSERT INTO users (username, email, city, latitude, longitude) VALUES
('alice_smith', 'alice@example.com', 'Toronto', 43.651070, -79.347015),
('bob_jones', 'bob@example.com', 'New York', 40.712776, -74.005974),
('charlie_lee', 'charlie@example.com', 'San Francisco', 37.774929, -122.419418),
('diana_kim', 'diana@example.com', 'London', 51.507351, -0.127758),
('eric_wang', 'eric@example.com', 'Tokyo', 35.689487, 139.691711),
('fiona_chen', 'fiona@example.com', 'Toronto', 43.653226, -79.383184),
('george_park', 'george@example.com', 'Los Angeles', 34.052235, -118.243683),
('hannah_liu', 'hannah@example.com', 'Chicago', 41.878113, -87.629799),
('ian_brown', 'ian@example.com', 'Paris', 48.856613, 2.352222),
('julia_davis', 'julia@example.com', 'Sydney', -33.868820, 151.209290);

-- Create index on user_id for faster lookups
CREATE INDEX idx_users_id ON users(user_id);
CREATE INDEX idx_users_city ON users(city);

-- Verify data
SELECT COUNT(*) as total_users FROM users;
SELECT city, COUNT(*) as users_per_city FROM users GROUP BY city;
