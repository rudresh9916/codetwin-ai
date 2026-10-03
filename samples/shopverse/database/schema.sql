CREATE TABLE users (id BIGSERIAL PRIMARY KEY, name TEXT, email TEXT UNIQUE, password_hash TEXT, role TEXT, active BOOLEAN, last_login_at TIMESTAMP);
CREATE TABLE products (id BIGSERIAL PRIMARY KEY, name TEXT, description TEXT, price NUMERIC(10,2), category TEXT, image_url TEXT, rating DOUBLE PRECISION);
CREATE TABLE orders (id BIGSERIAL PRIMARY KEY, customer_id BIGINT REFERENCES users(id), total NUMERIC(10,2), status TEXT, shipping_address TEXT, created_at TIMESTAMP);
CREATE TABLE order_items (id BIGSERIAL PRIMARY KEY, order_id BIGINT REFERENCES orders(id), product_id BIGINT REFERENCES products(id), quantity INT, unit_price NUMERIC(10,2));
CREATE TABLE payments (id BIGSERIAL PRIMARY KEY, order_id BIGINT REFERENCES orders(id), amount NUMERIC(10,2), currency TEXT, status TEXT, provider_reference TEXT, attempts INT, processed_at TIMESTAMP);
CREATE TABLE inventory (id BIGSERIAL PRIMARY KEY, product_id BIGINT REFERENCES products(id), quantity INT, warehouse TEXT);
CREATE TABLE reviews (id BIGSERIAL PRIMARY KEY, product_id BIGINT REFERENCES products(id), user_id BIGINT REFERENCES users(id), stars INT, comment TEXT);
