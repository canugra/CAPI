CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wa_id TEXT,
    phone_number TEXT,
    customer_name TEXT,
    source TEXT DEFAULT 'UNKNOWN',
    status TEXT DEFAULT 'NEW',
    first_message_at DATETIME,
    last_message_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attribution_touches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    ctwa_clid TEXT,
    source_id TEXT,
    source_type TEXT,
    source_url TEXT,
    headline TEXT,
    body TEXT,
    media_type TEXT,
    raw_referral_json TEXT,
    received_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    wa_message_id TEXT UNIQUE,
    direction TEXT,
    message_type TEXT,
    received_at DATETIME,
    raw_payload_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT UNIQUE,
    lead_id INTEGER,
    status TEXT DEFAULT 'PENDING',
    value INTEGER,
    currency TEXT DEFAULT 'IDR',
    paid_at DATETIME,
    lost_at DATETIME,
    notes TEXT,
    created_by TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS conversion_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    platform TEXT,
    event_name TEXT,
    event_id TEXT UNIQUE,
    ctwa_clid TEXT,
    event_time DATETIME,
    value INTEGER,
    currency TEXT,
    status TEXT DEFAULT 'PENDING',
    attempt_count INTEGER DEFAULT 0,
    last_attempt_at DATETIME,
    sent_at DATETIME,
    http_status INTEGER,
    provider_response_json TEXT,
    last_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(order_id) REFERENCES orders(id),
    UNIQUE(order_id, platform, event_name)
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT,
    external_event_key TEXT,
    event_type TEXT,
    payload_json TEXT,
    status TEXT,
    processed_at DATETIME,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id TEXT,
    action TEXT,
    entity_type TEXT,
    entity_id TEXT,
    before_json TEXT,
    after_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
