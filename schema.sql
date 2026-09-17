CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    wa_id VARCHAR(255),
    phone_number VARCHAR(255),
    customer_name VARCHAR(255),
    source VARCHAR(50) DEFAULT 'UNKNOWN',
    status VARCHAR(50) DEFAULT 'NEW',
    first_message_at DATETIME,
    last_message_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attribution_touches (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    lead_id INTEGER,
    ctwa_clid VARCHAR(255),
    source_id VARCHAR(255),
    source_type VARCHAR(255),
    source_url TEXT,
    headline TEXT,
    body TEXT,
    media_type VARCHAR(255),
    raw_referral_json TEXT,
    received_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    lead_id INTEGER,
    wa_message_id VARCHAR(255) UNIQUE,
    direction VARCHAR(50),
    message_type VARCHAR(50),
    received_at DATETIME,
    raw_payload_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    order_number VARCHAR(255) UNIQUE,
    lead_id INTEGER,
    status VARCHAR(50),
    value INTEGER,
    currency VARCHAR(10) DEFAULT 'IDR',
    paid_at DATETIME,
    lost_at DATETIME,
    notes TEXT,
    created_by VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY(lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS conversion_events (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    order_id INTEGER,
    platform VARCHAR(50),
    event_name VARCHAR(255),
    event_id VARCHAR(255) UNIQUE,
    ctwa_clid VARCHAR(255),
    event_time DATETIME,
    value INTEGER,
    currency VARCHAR(10),
    status VARCHAR(50) DEFAULT 'PENDING',
    attempt_count INTEGER DEFAULT 0,
    last_attempt_at DATETIME,
    sent_at DATETIME,
    http_status INTEGER,
    provider_response_json TEXT,
    last_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY(order_id) REFERENCES orders(id),
    UNIQUE(order_id, platform, event_name)
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    provider VARCHAR(50),
    external_event_key VARCHAR(255),
    event_type VARCHAR(50),
    payload_json TEXT,
    status VARCHAR(50),
    processed_at DATETIME,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    actor_id VARCHAR(255),
    action VARCHAR(255),
    entity_type VARCHAR(255),
    entity_id VARCHAR(255),
    before_json TEXT,
    after_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_settings (
    setting_key VARCHAR(255) PRIMARY KEY,
    setting_value TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
