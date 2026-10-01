-- Schema definition for Seat Reservation System

-- 1. SHOWS
CREATE TABLE IF NOT EXISTS shows (
    id TEXT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price_paise BIGINT NOT NULL,
    per_user_limit INT NOT NULL DEFAULT 4,
    created_on TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. SEATS
CREATE TABLE IF NOT EXISTS seats (
    id BIGSERIAL PRIMARY KEY,
    show_id TEXT NOT NULL REFERENCES shows(id) ON DELETE RESTRICT,
    seat_number VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE', -- 'AVAILABLE' | 'CONFIRMED'
    updated_on TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_show_seat UNIQUE (show_id, seat_number)
);

CREATE INDEX IF NOT EXISTS idx_seats_show_lookup ON seats(show_id, seat_number);
CREATE INDEX IF NOT EXISTS idx_seats_show_status ON seats(show_id, status);

-- 3. RESERVATIONS
CREATE TABLE IF NOT EXISTS reservations (
    id TEXT PRIMARY KEY,
    show_id TEXT NOT NULL REFERENCES shows(id) ON DELETE RESTRICT,
    user_id VARCHAR(255) NOT NULL,
    amount_paise BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'CONFIRMED', -- 'CONFIRMED' | 'CANCELLED'
    created_on TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reservations_user_show ON reservations(user_id, show_id);

-- 4. RESERVATION_SEATS (Mapping with per-seat price)
CREATE TABLE IF NOT EXISTS reservation_seats (
    id BIGSERIAL PRIMARY KEY,
    reservation_id TEXT NOT NULL REFERENCES reservations(id) ON DELETE RESTRICT,
    seat_id BIGINT NOT NULL REFERENCES seats(id) ON DELETE RESTRICT,
    seat_number VARCHAR(50) NOT NULL,
    price_paise BIGINT NOT NULL,
    created_on TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_res_seats_res_id ON reservation_seats(reservation_id);

-- 5. IDEMPOTENCY_RECORDS
CREATE TABLE IF NOT EXISTS idempotency_records (
    idempotency_key VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    show_id TEXT NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    response_status_code INT NOT NULL,
    response_body TEXT NOT NULL,
    created_on TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
